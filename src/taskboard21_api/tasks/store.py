"""Postgres-backed task store."""

from __future__ import annotations

import functools
import os
import threading
import uuid

import psycopg
import structlog

from .models import Task, TaskCreate
from .schema import MIGRATIONS, SCHEMA_LOCK_ID

logger = structlog.get_logger()

_STATEMENT_TIMEOUT_MS = 2000
_PING_TIMEOUT_MS = 1000


class StorageUnavailableError(Exception):
    """The database cannot be reached or did not answer in time."""


class TaskStore:
    """Keeps tasks in Postgres, one short-lived connection per call."""

    def __init__(self, dsn: str | None = None) -> None:
        self._dsn = os.environ.get("DATABASE_URL", "") if dsn is None else dsn
        self._schema_ready = False
        self._schema_flag_lock = threading.Lock()
        self._missing_logged = False

    def _connect(self, statement_timeout_ms: int) -> psycopg.Connection[tuple[object, ...]]:
        if not self._dsn:
            if not self._missing_logged:
                self._missing_logged = True
                logger.error("database_url_missing")
            raise StorageUnavailableError("Task storage is unavailable")
        return psycopg.connect(
            self._dsn,
            connect_timeout=1,
            options=f"-c statement_timeout={statement_timeout_ms}",
        )

    def _apply_schema(self, conn: psycopg.Connection[tuple[object, ...]]) -> None:
        if self._schema_ready:
            return
        with conn.transaction():
            conn.execute("SELECT pg_advisory_xact_lock(%s)", (SCHEMA_LOCK_ID,))
            for statement in MIGRATIONS:
                conn.execute(statement.encode())
        with self._schema_flag_lock:
            self._schema_ready = True

    @staticmethod
    def _unavailable(exc: Exception) -> StorageUnavailableError:
        logger.warning("task_storage_unavailable", error=type(exc).__name__)
        return StorageUnavailableError("Task storage is unavailable")

    def ensure_schema(self) -> None:
        """Create the schema if this instance has not applied it yet."""
        try:
            with self._connect(_STATEMENT_TIMEOUT_MS) as conn:
                self._apply_schema(conn)
        except (psycopg.OperationalError, psycopg.InterfaceError) as exc:
            raise self._unavailable(exc) from exc

    def add(self, data: TaskCreate) -> Task:
        """Assign a new id, store the task and return it."""
        try:
            with self._connect(_STATEMENT_TIMEOUT_MS) as conn:
                self._apply_schema(conn)
                row = conn.execute(
                    "INSERT INTO tasks (id, title, due_date) VALUES (%s, %s, %s) "
                    "RETURNING id::text, title, due_date",
                    (str(uuid.uuid4()), data.title, data.due_date),
                ).fetchone()
        except (psycopg.OperationalError, psycopg.InterfaceError) as exc:
            raise self._unavailable(exc) from exc
        if row is None:
            raise RuntimeError("INSERT ... RETURNING returned no row")
        task = Task(id=str(row[0]), title=str(row[1]), due_date=row[2])  # type: ignore[arg-type]
        logger.info("task_created", task_id=task.id)
        return task

    def list(self) -> list[Task]:
        """Return all tasks in creation order."""
        try:
            with self._connect(_STATEMENT_TIMEOUT_MS) as conn:
                self._apply_schema(conn)
                rows = conn.execute(
                    "SELECT id::text, title, due_date FROM tasks ORDER BY seq"
                ).fetchall()
        except (psycopg.OperationalError, psycopg.InterfaceError) as exc:
            raise self._unavailable(exc) from exc
        return [Task(id=str(r[0]), title=str(r[1]), due_date=r[2]) for r in rows]  # type: ignore[arg-type]

    def ping(self) -> bool:
        """True when the schema is in place and the database answers; never raises."""
        try:
            with self._connect(_PING_TIMEOUT_MS) as conn:
                self._apply_schema(conn)
                conn.execute("SELECT 1")
        except (StorageUnavailableError, psycopg.OperationalError, psycopg.InterfaceError):
            return False
        return True


@functools.lru_cache(maxsize=1)
def get_task_store() -> TaskStore:
    """FastAPI dependency returning the process-wide store."""
    return TaskStore()
