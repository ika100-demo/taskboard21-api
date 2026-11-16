"""Shared pytest fixtures."""

from __future__ import annotations

import os
from collections.abc import Iterator

import psycopg
import pytest
from fastapi.testclient import TestClient
from pytest_postgresql import factories
from pytest_postgresql.janitor import DatabaseJanitor

from taskboard21_api.main import app
from taskboard21_api.tasks.store import get_task_store

postgresql_proc = factories.postgresql_proc()


@pytest.fixture(scope="session")
def database_url(request: pytest.FixtureRequest) -> Iterator[str]:
    """DSN of a throwaway test database (``TEST_DATABASE_URL`` when set)."""
    external = os.environ.get("TEST_DATABASE_URL")
    if external:
        yield external
        return
    proc = request.getfixturevalue("postgresql_proc")
    janitor = DatabaseJanitor(
        user=proc.user,
        host=proc.host,
        port=proc.port,
        dbname="taskboard_test",
    )
    janitor.init()
    try:
        yield f"postgresql://{proc.user}@{proc.host}:{proc.port}/taskboard_test"
    finally:
        janitor.drop()


@pytest.fixture(scope="session", autouse=True)
def _database_env(database_url: str) -> Iterator[None]:
    """Point the application at the test database."""
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = database_url
    get_task_store.cache_clear()
    yield
    if previous is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = previous
    get_task_store.cache_clear()


@pytest.fixture(autouse=True)
def _empty_tasks(database_url: str) -> None:
    """Start every test with no tasks."""
    with psycopg.connect(database_url, autocommit=True) as conn:
        row = conn.execute("SELECT to_regclass('tasks')").fetchone()
        if row is not None and row[0] is not None:
            conn.execute("TRUNCATE tasks")


@pytest.fixture()
def client() -> TestClient:
    """A TestClient for the FastAPI application."""
    return TestClient(app)
