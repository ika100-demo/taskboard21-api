"""Process-local, thread-safe task store."""

from __future__ import annotations

import threading
import uuid

import structlog

from .models import Task, TaskCreate

logger = structlog.get_logger()


class TaskStore:
    """Keeps tasks in creation order; lost on restart."""

    def __init__(self) -> None:
        self._tasks: list[Task] = []
        self._lock = threading.Lock()

    def add(self, data: TaskCreate) -> Task:
        """Assign a new id, store the task and return it."""
        task = Task(id=str(uuid.uuid4()), title=data.title, due_date=data.due_date)
        with self._lock:
            self._tasks.append(task)
        logger.info("task_created", task_id=task.id)
        return task

    def list(self) -> list[Task]:
        """Return a copy of all tasks in creation order."""
        with self._lock:
            return list(self._tasks)


_store = TaskStore()


def get_task_store() -> TaskStore:
    """FastAPI dependency returning the process-wide store."""
    return _store
