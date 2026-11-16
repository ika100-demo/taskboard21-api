"""Smoke tests for spec 001 (AC-001.1, AC-001.2, AC-001.5): reach the service by URL only."""

from __future__ import annotations

import uuid

import httpx
import pytest


@pytest.mark.smoke
@pytest.mark.writes
def test_smoke_ac_001_1_create_task_with_due_date(smoke_base_url: str) -> None:
    title = f"smoke-{uuid.uuid4()}"
    response = httpx.post(
        smoke_base_url + "/tasks", json={"title": title, "due_date": "2026-12-01"}, timeout=10
    )
    assert response.status_code == 201
    body = response.json()
    assert body["id"]
    assert body["title"] == title
    assert body["due_date"] == "2026-12-01"


@pytest.mark.smoke
@pytest.mark.writes
def test_smoke_ac_001_2_create_task_without_due_date(smoke_base_url: str) -> None:
    title = f"smoke-{uuid.uuid4()}"
    response = httpx.post(smoke_base_url + "/tasks", json={"title": title}, timeout=10)
    assert response.status_code == 201
    assert response.json()["due_date"] is None


@pytest.mark.smoke
@pytest.mark.writes
def test_smoke_ac_001_5_list_in_creation_order(smoke_base_url: str) -> None:
    created = []
    for _ in range(3):
        response = httpx.post(
            smoke_base_url + "/tasks", json={"title": f"smoke-{uuid.uuid4()}"}, timeout=10
        )
        assert response.status_code == 201
        created.append(response.json())
    listing = httpx.get(smoke_base_url + "/tasks", timeout=10)
    assert listing.status_code == 200
    ids = [t["id"] for t in listing.json()]
    own = [i for i in ids if i in {t["id"] for t in created}]
    assert own == [t["id"] for t in created]
    by_id = {t["id"]: t for t in listing.json()}
    for task in created:
        assert by_id[task["id"]] == task


@pytest.mark.smoke
def test_smoke_ac_001_5_list_tasks_is_readable(smoke_base_url: str) -> None:
    response = httpx.get(smoke_base_url + "/tasks", timeout=10)
    assert response.status_code == 200
    assert isinstance(response.json(), list)
