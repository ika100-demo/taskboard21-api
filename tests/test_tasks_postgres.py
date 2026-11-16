"""Acceptance tests for spec 002: tasks are kept in Postgres."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from fastapi.testclient import TestClient

from taskboard21_api.main import app

UNREACHABLE_DSN = "postgresql://u:p@127.0.0.1:1/x"
UNAVAILABLE = {"detail": "Task storage is unavailable"}


@pytest.fixture()
def dsn(request: pytest.FixtureRequest) -> str:
    """The test database DSN (the session fixture `database_url`)."""
    try:
        return str(request.getfixturevalue("database_url"))
    except pytest.FixtureLookupError:
        # Until the Postgres test infrastructure exists the tests still fail on the
        # missing behaviour (TaskStore takes no dsn), not on a missing fixture.
        return UNREACHABLE_DSN


@contextmanager
def client_for(store: Any) -> Iterator[TestClient]:
    from taskboard21_api.tasks.store import get_task_store

    app.dependency_overrides[get_task_store] = lambda: store
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_task_store, None)


def _store(dsn: str) -> Any:
    from taskboard21_api.tasks.store import TaskStore

    return TaskStore(dsn)


def _count_rows(dsn: str) -> int:
    import psycopg

    with psycopg.connect(dsn) as conn:
        row = conn.execute("SELECT count(*) FROM tasks").fetchone()
    assert row is not None
    return int(row[0])


def _create(client: TestClient, title: str, due: str | None = None) -> dict[str, Any]:
    response = client.post("/tasks", json={"title": title, "due_date": due})
    assert response.status_code == 201
    body: dict[str, Any] = response.json()
    return body


def test_tasks_survive_restart_in_creation_order(dsn: str):  # AC-002.1
    created = []
    with client_for(_store(dsn)) as first:
        for title, due in [("A", "2026-12-01"), ("B", None), ("C", "2027-01-15")]:
            created.append(_create(first, title, due))
    assert _count_rows(dsn) == 3  # the tasks are in Postgres, not in process memory
    # restart: a fresh store (and schema application) over the same database
    with client_for(_store(dsn)) as second:
        response = second.get("/tasks")
    assert response.status_code == 200
    assert response.json() == created
    assert [t["title"] for t in response.json()] == ["A", "B", "C"]


def test_empty_database_lists_empty_array_also_after_restart(dsn: str):  # AC-002.2
    with client_for(_store(dsn)) as first:
        response = first.get("/tasks")
        assert response.status_code == 200
        assert response.json() == []
    with client_for(_store(dsn)) as restarted:
        response = restarted.get("/tasks")
    assert response.status_code == 200
    assert response.json() == []


def test_two_instances_share_tasks_and_ids_are_unique(dsn: str):  # AC-002.3
    store_one, store_two = _store(dsn), _store(dsn)
    with client_for(store_one) as one:
        first = _create(one, "from one")
    with client_for(store_two) as two:
        second = _create(two, "from two")
        assert _count_rows(dsn) == 2  # both tasks are stored in Postgres
        listed_two = two.get("/tasks").json()
    with client_for(store_one) as one:
        listed_one = one.get("/tasks").json()
    assert listed_one == listed_two == [first, second]
    assert listed_one[-1] == second
    assert len({t["id"] for t in listed_one}) == len(listed_one) == 2


@pytest.mark.parametrize(
    "payload, expected_due",
    [
        ({"title": "Buy milk", "due_date": "2026-12-01"}, "2026-12-01"),
        ({"title": "Buy milk"}, None),
    ],
    ids=["with-due-date", "title-only"],
)
def test_create_then_list_returns_same_fields(
    dsn: str, payload: dict, expected_due: str | None
):  # AC-002.4
    with client_for(_store(dsn)) as client:
        response = client.post("/tasks", json=payload)
        assert response.status_code == 201
        body = response.json()
        assert body["id"]
        assert body["title"] == "Buy milk"
        assert body["due_date"] == expected_due
        listed = client.get("/tasks").json()
    assert listed == [body]


@pytest.mark.parametrize(
    "payload, field",
    [
        ({"title": ""}, "title"),
        ({"title": "x" * 201}, "title"),
        ({"title": "a\u0000b"}, "title"),
        ({"title": "Buy milk", "due_date": "2026-02-30"}, "due_date"),
    ],
    ids=["empty", "too-long", "nul-char", "bad-date"],
)
def test_invalid_input_is_422_and_stores_nothing(dsn: str, payload: dict, field: str):  # AC-002.4
    with client_for(_store(dsn)) as client:
        response = client.post("/tasks", json=payload)
        assert response.status_code == 422
        locs = [err["loc"] for err in response.json()["detail"]]
        assert locs
        assert all(loc[-1] == field for loc in locs)
        assert client.get("/tasks").json() == []
    assert _count_rows(dsn) == 0


def _timed(call: Callable[[], Any]) -> tuple[Any, float]:
    start = time.monotonic()
    result = call()
    return result, time.monotonic() - start


def test_unreachable_database_gives_503_and_stores_nothing(dsn: str):  # AC-002.5
    # make sure the schema exists so that the row count below is meaningful
    _store(dsn).list()
    with client_for(_store(UNREACHABLE_DSN)) as client:
        got, got_s = _timed(lambda: client.get("/tasks"))
        posted, post_s = _timed(lambda: client.post("/tasks", json={"title": "Lost"}))
    assert got.status_code == 503
    assert got.json() == UNAVAILABLE
    assert posted.status_code == 503
    assert posted.json() == UNAVAILABLE
    assert got_s < 3
    assert post_s < 3
    assert _count_rows(dsn) == 0


def test_readiness_follows_database_and_tasks_survive_outage(dsn: str):  # AC-002.6
    with client_for(_store(dsn)) as client:
        created = [_create(client, "before 1"), _create(client, "before 2")]
        before = client.get("/ready")
        assert before.status_code == 200
        assert before.json() == {"status": "ready"}
    with client_for(_store(UNREACHABLE_DSN)) as down:
        response = down.get("/ready")
        assert response.status_code == 503
        assert response.json() == {"status": "not ready"}
        assert down.get("/health").status_code == 200
    with client_for(_store(dsn)) as back:
        ready = back.get("/ready")
        assert ready.status_code == 200
        assert ready.json() == {"status": "ready"}
        listed = back.get("/tasks")
    assert listed.status_code == 200
    assert listed.json() == created


def test_same_instance_becomes_ready_when_database_comes_back(dsn: str):  # AC-002.6
    import uuid

    import psycopg
    from psycopg import sql
    from psycopg.conninfo import make_conninfo

    # one store whose database does not exist yet = an outage for that instance
    name = f"outage_{uuid.uuid4().hex[:12]}"
    store = _store(make_conninfo(dsn, dbname=name))
    with client_for(store) as client:
        down = client.get("/ready")
        assert down.status_code == 503
        assert down.json() == {"status": "not ready"}
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            up = client.get("/ready")
            assert up.status_code == 200
            assert up.json() == {"status": "ready"}
            created = _create(client, "after outage")
            assert client.get("/tasks").json() == [created]
        finally:
            with psycopg.connect(dsn, autocommit=True) as admin:
                drop = sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)")
                admin.execute(drop.format(sql.Identifier(name)))
