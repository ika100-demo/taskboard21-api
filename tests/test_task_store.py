"""Unit tests for the task models and the in-memory store."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from pydantic import ValidationError

from taskboard21_api.tasks.models import TaskCreate
from taskboard21_api.tasks.store import TaskStore, get_task_store


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
