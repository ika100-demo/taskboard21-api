"""Acceptance tests for spec 001: create and list tasks in memory."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from taskboard21_api.main import app


@pytest.fixture()
def task_client() -> Iterator[TestClient]:
    """A client whose app uses a fresh, empty TaskStore."""
    from taskboard21_api.tasks.store import TaskStore, get_task_store

    store = TaskStore()
    app.dependency_overrides[get_task_store] = lambda: store
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_task_store, None)


def _locs(response: Any) -> list[list[Any]]:
    return [err["loc"] for err in response.json()["detail"]]


def test_create_task_with_due_date():  # AC-001.1
    from taskboard21_api.tasks.store import TaskStore, get_task_store

    store = TaskStore()
    app.dependency_overrides[get_task_store] = lambda: store
    try:
        response = TestClient(app).post(
            "/tasks", json={"title": "Buy milk", "due_date": "2026-12-01"}
        )
    finally:
        app.dependency_overrides.pop(get_task_store, None)
    assert response.status_code == 201
    body = response.json()
    assert isinstance(body["id"], str)
    assert body["id"]
    assert body["title"] == "Buy milk"
    assert body["due_date"] == "2026-12-01"


def test_create_task_without_due_date_is_null(task_client: TestClient):  # AC-001.2
    response = task_client.post("/tasks", json={"title": "Buy milk"})
    assert response.status_code == 201
    assert response.json()["due_date"] is None


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"title": 123},
        {"title": None},
        {"title": ""},
        {"title": "   "},
        {"title": "x" * 201},
    ],
    ids=["missing", "int", "null", "empty", "whitespace", "too-long"],
)
def test_invalid_title_rejected(task_client: TestClient, payload: dict):  # AC-001.3
    response = task_client.post("/tasks", json=payload)
    assert response.status_code == 422
    assert all(loc[-1] == "title" for loc in _locs(response))
    assert _locs(response)
    assert task_client.get("/tasks").json() == []


def test_title_of_200_chars_accepted(task_client: TestClient):  # AC-001.3
    response = task_client.post("/tasks", json={"title": "x" * 200})
    assert response.status_code == 201


@pytest.mark.parametrize(
    "due",
    ["2026-02-30", "tomorrow", "2026-12-01T00:00:00", 20261201],
    ids=["not-a-date", "word", "datetime", "number"],
)
def test_invalid_due_date_rejected(task_client: TestClient, due: Any):  # AC-001.4
    response = task_client.post("/tasks", json={"title": "Buy milk", "due_date": due})
    assert response.status_code == 422
    assert _locs(response)
    assert all(loc[-1] == "due_date" for loc in _locs(response))
    assert task_client.get("/tasks").json() == []


def test_list_returns_tasks_in_creation_order(task_client: TestClient):  # AC-001.5
    created = []
    for title, due in [("A", "2026-12-01"), ("B", None), ("C", "2027-01-15")]:
        response = task_client.post("/tasks", json={"title": title, "due_date": due})
        assert response.status_code == 201
        created.append(response.json())
    response = task_client.get("/tasks")
    assert response.status_code == 200
    assert response.json() == created
    assert [t["title"] for t in response.json()] == ["A", "B", "C"]


def test_list_empty_initially(task_client: TestClient):  # AC-001.6
    response = task_client.get("/tasks")
    assert response.status_code == 200
    assert response.json() == []


def test_same_title_tasks_get_distinct_ids(task_client: TestClient):  # AC-001.7
    first = task_client.post("/tasks", json={"title": "Same"}).json()
    second = task_client.post("/tasks", json={"title": "Same"}).json()
    listed = task_client.get("/tasks").json()
    assert len(listed) == 2
    assert first["id"] != second["id"]
    assert {t["id"] for t in listed} == {first["id"], second["id"]}
