"""HTTP routes for tasks."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from .models import Task, TaskCreate
from .store import StorageUnavailableError, TaskStore, get_task_store

router = APIRouter(tags=["tasks"])

_UNAVAILABLE: dict[int | str, dict[str, Any]] = {
    503: {"description": "Task storage is unavailable"},
}


def _unavailable() -> HTTPException:
    return HTTPException(status_code=503, detail="Task storage is unavailable")


@router.post("/tasks", status_code=201, response_model=Task, responses=_UNAVAILABLE)
def create_task(body: TaskCreate, store: TaskStore = Depends(get_task_store)) -> Task:  # noqa: B008
    """Create a task and return it with its new id."""
    try:
        return store.add(body)
    except StorageUnavailableError:
        raise _unavailable() from None


@router.get("/tasks", response_model=list[Task], responses=_UNAVAILABLE)
def list_tasks(store: TaskStore = Depends(get_task_store)) -> list[Task]:  # noqa: B008
    """List all tasks in creation order."""
    try:
        return store.list()
    except StorageUnavailableError:
        raise _unavailable() from None
