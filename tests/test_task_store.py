"""Unit tests for the task models and the Postgres store."""

from __future__ import annotations

import threading
from datetime import date
from typing import Any

import pytest
from pydantic import ValidationError

from taskboard21_api.tasks.models import TaskCreate
from taskboard21_api.tasks.store import StorageUnavailableError, TaskStore, get_task_store

UNREACHABLE_DSN = "postgresql://u:p@127.0.0.1:1/x"


def test_valid_title_kept_exactly():
    assert TaskCreate(title="  Buy milk ").title == "  Buy milk "


@pytest.mark.parametrize("title", ["", "   ", "\t\n", "x" * 201])
def test_invalid_title_rejected(title: str):
    with pytest.raises(ValidationError):
        TaskCreate(title=title)


def test_title_of_200_chars_accepted():
    assert len(TaskCreate(title="x" * 200).title) == 200


@pytest.mark.parametrize("title", [123, None, ["a"]])
def test_non_string_title_rejected(title: Any):
    with pytest.raises(ValidationError):
        TaskCreate.model_validate({"title": title})


def test_title_required():
    with pytest.raises(ValidationError):
        TaskCreate.model_validate({})


@pytest.mark.parametrize(
    "due",
    ["tomorrow", "2026-12-01T00:00:00", "2026-02-30", 1764547200, 20261201, "2026-1-1"],
)
def test_invalid_due_date_rejected(due: Any):
    with pytest.raises(ValidationError):
        TaskCreate.model_validate({"title": "t", "due_date": due})


def test_due_date_parsed_and_past_accepted():
    task = TaskCreate.model_validate({"title": "t", "due_date": "2001-01-02"})
    assert task.due_date == date(2001, 1, 2)


def test_due_date_omitted_or_null():
    assert TaskCreate(title="t").due_date is None
    assert TaskCreate.model_validate({"title": "t", "due_date": None}).due_date is None


def test_client_sent_id_ignored():
    assert not hasattr(TaskCreate.model_validate({"title": "t", "id": "x"}), "id")


def test_store_starts_empty():
    assert TaskStore().list() == []


def test_store_keeps_creation_order():
    store = TaskStore()
    for name in ("a", "b", "c"):
        store.add(TaskCreate(title=name))
    assert [t.title for t in store.list()] == ["a", "b", "c"]


def test_store_assigns_distinct_ids_for_equal_titles():
    store = TaskStore()
    first = store.add(TaskCreate(title="same"))
    second = store.add(TaskCreate(title="same"))
    assert first.id != second.id


def test_store_list_returns_copy():
    store = TaskStore()
    store.add(TaskCreate(title="a"))
    store.list().clear()
    assert len(store.list()) == 1


def test_get_task_store_is_singleton():
    assert get_task_store() is get_task_store()


def test_ensure_schema_is_idempotent(database_url: str):
    store = TaskStore(database_url)
    store.ensure_schema()
    store.ensure_schema()
    TaskStore(database_url).ensure_schema()
    assert store.ping() is True


def test_ensure_schema_from_two_threads(database_url: str):
    errors: list[Exception] = []

    def run() -> None:
        try:
            TaskStore(database_url).ensure_schema()
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []


def test_nul_title_rejected():
    with pytest.raises(ValidationError):
        TaskCreate(title="a\x00b")


def test_unreachable_dsn_raises_storage_unavailable():
    store = TaskStore(UNREACHABLE_DSN)
    with pytest.raises(StorageUnavailableError):
        store.list()
    with pytest.raises(StorageUnavailableError):
        store.add(TaskCreate(title="x"))


def test_ping_false_when_unreachable_or_unconfigured():
    assert TaskStore(UNREACHABLE_DSN).ping() is False
    assert TaskStore("").ping() is False
