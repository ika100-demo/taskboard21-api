---
spec_id: 002-keep-tasks-in-postgres-so-they-survive
shape: service-python
spec_hash: 0d035bf434bb
summary: Store tasks in Postgres (psycopg 3, service-owned schema), 503 on outage, database-backed readiness
tasks:
  - id: t1
    title: Replace the in-memory TaskStore with a Postgres store, schema and test database
    files: [pyproject.toml, uv.lock, devbox.json, devbox.lock, src/taskboard21_api/tasks/__init__.py, src/taskboard21_api/tasks/models.py, src/taskboard21_api/tasks/schema.py, src/taskboard21_api/tasks/store.py, tests/conftest.py, tests/test_task_store.py]
    covers: [AC-002.1, AC-002.2, AC-002.3, AC-002.4, AC-002.5, AC-002.6]
    parallel_safe: true
    depends_on: []
    done: true
  - id: t2
    title: Answer 503 on storage outage, check the database in /ready, apply the schema at startup
    files: [src/taskboard21_api/tasks/router.py, src/taskboard21_api/main.py, docs/env-vars.md]
    covers: [AC-002.1, AC-002.4, AC-002.5, AC-002.6]
    parallel_safe: true
    depends_on: [t1]
    done: true
---

# Plan — 002 Keep tasks in Postgres so they survive restarts and are shared by every instance

Contract, schema and decisions: [design.md](design.md).

## t1 — Replace the in-memory TaskStore with a Postgres store, schema and test database

**Files:** pyproject.toml, uv.lock, devbox.json, devbox.lock, src/taskboard21_api/tasks/__init__.py, src/taskboard21_api/tasks/models.py, src/taskboard21_api/tasks/schema.py, src/taskboard21_api/tasks/store.py, tests/conftest.py, tests/test_task_store.py
**Covers:** AC-002.1, AC-002.2, AC-002.3, AC-002.4, AC-002.5, AC-002.6
**Goal:** tasks are written to and read from Postgres through the unchanged `TaskStore` interface, ordered by a database identity, with an idempotent, lock-protected schema; the test suite runs against a real throwaway Postgres. After this task the existing endpoints already persist and share tasks; the 503 mapping and readiness follow in t2.

**Implementation notes:**
- Dependencies: `psycopg[binary]>=3.2` in `[project].dependencies`, `pytest-postgresql>=6` in the `dev` extra; refresh `uv.lock` inside the devbox environment (`devbox run -- uv lock`), never `pip`/`uv add` directly. Add `postgresql@16` to the devbox `packages` (only the packages list; leave the template recipes alone) and let devbox update `devbox.lock`.
- `schema.py`: `SCHEMA_LOCK_ID = 2002001` and `MIGRATIONS: list[str]` holding the `CREATE TABLE IF NOT EXISTS tasks (...)` statement from design.md § Data.
- `store.py`: remove the list/lock implementation. `StorageUnavailableError`; `TaskStore(dsn: str | None = None)` reads `os.environ.get("DATABASE_URL", "")` when `dsn` is None; `_connect(statement_timeout_ms)` = `psycopg.connect(dsn, connect_timeout=1, options=f"-c statement_timeout={ms}")`.
- `ensure_schema()`: one transaction, `SELECT pg_advisory_xact_lock(%s)` with `SCHEMA_LOCK_ID`, then each statement of `MIGRATIONS`; set a per-instance flag under a `threading.Lock` after success. `add`/`list` call the same logic on their own connection while the flag is unset.
- `add`: `INSERT INTO tasks (id, title, due_date) VALUES (%s, %s, %s) RETURNING id::text, title, due_date` with `str(uuid.uuid4())`, committed on leaving the connection block; keep the `task_created` log line with `task_id` (never the title).
- `list`: `SELECT id::text, title, due_date FROM tasks ORDER BY seq`.
- `ping() -> bool`: ensure schema if needed, `SELECT 1` with `statement_timeout_ms=1000`; returns False on any `StorageUnavailableError`, never raises.
- Map `psycopg.OperationalError` and `psycopg.InterfaceError` to `StorageUnavailableError` (log `task_storage_unavailable` with the exception class name only); an empty DSN raises it too and logs `database_url_missing` once per instance. Never log the DSN.
- `get_task_store()` becomes `@functools.lru_cache(maxsize=1)` so `cache_clear()` works in tests; it stays the FastAPI dependency.
- `models.py`: the `title` validator also raises `ValueError` when `"\x00" in v`. `tasks/__init__.py`: docstring says "models and the Postgres store".
- `tests/conftest.py`: session fixture `database_url` (use `TEST_DATABASE_URL` if set, else pytest-postgresql `postgresql_proc` plus a `DatabaseJanitor` database); an autouse session fixture sets `os.environ["DATABASE_URL"]` and calls `get_task_store.cache_clear()`; an autouse function fixture empties `tasks` when `to_regclass('tasks')` is not null. Keep the `client` fixture. `tests/test_task_store.py`: keep the existing tests passing; add unit tests for schema idempotence (twice, and from two threads), NUL titles, and an unreachable DSN raising `StorageUnavailableError` and `ping()` returning False.

**Done when:** spec 001's acceptance tests and `tests/test_task_store.py` pass against the test Postgres; the acceptance tests for AC-002.1 to AC-002.4 pass (AC-002.5 and AC-002.6 need t2's 503 mapping and readiness); `devbox run quality` is green.

## t2 — Answer 503 on storage outage, check the database in /ready, apply the schema at startup

**Files:** src/taskboard21_api/tasks/router.py, src/taskboard21_api/main.py, docs/env-vars.md
**Covers:** AC-002.1, AC-002.4, AC-002.5, AC-002.6
**Goal:** the HTTP side of the contract in design.md: `503 {"detail": "Task storage is unavailable"}` from both task endpoints when the database is unreachable, a readiness probe that follows the database, and schema creation at startup.

**Implementation notes:**
- `router.py`: in both handlers, `except StorageUnavailableError: raise HTTPException(status_code=503, detail="Task storage is unavailable") from None`. Add `responses={503: ...}` so OpenAPI lists it.
- `main.py` `/ready`: `def ready(store: TaskStore = Depends(get_task_store))`; `store.ping()` True → `HealthResponse(status="ready")`, else `JSONResponse(status_code=503, content={"status": "not ready"})`. Tests override `get_task_store` to drive it.
- `main.py` lifespan (`contextlib.asynccontextmanager`, passed to `FastAPI(lifespan=...)`): call `get_task_store().ensure_schema()`; on `StorageUnavailableError` log `schema_deferred` as a warning and start anyway (the store applies it lazily later).
- `/health`, `/ping`, `/metrics`, middleware and tracing setup stay unchanged.
- `docs/env-vars.md`: a "Storage" section with `DATABASE_URL` (no default; unset means `/ready` and task endpoints answer 503; injected by the gitops entry from the `postgres` resource).

**Done when:** all acceptance tests for AC-002.1 to AC-002.6 and spec 001 pass, `tests/test_health.py` passes, and `devbox run ci` is green.
