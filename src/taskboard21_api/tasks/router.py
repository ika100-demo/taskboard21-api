"""HTTP routes for tasks."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from .models import Task, TaskCreate
from .store import TaskStore, get_task_store

router = APIRouter(tags=["tasks"])


@router.post("/tasks", status_code=201, response_model=Task)
def create_task(body: TaskCreate, store: TaskStore = Depends(get_task_store)) -> Task:  # noqa: B008
    """Create a task and return it with its new id."""
    return store.add(body)


@router.get("/tasks", response_model=list[Task])
def list_tasks(store: TaskStore = Depends(get_task_store)) -> list[Task]:  # noqa: B008
    """List all tasks in creation order."""
    return store.list()
