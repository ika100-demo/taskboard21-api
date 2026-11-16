# Design — 002 Keep tasks in Postgres so they survive restarts and are shared by every instance

## Decisions

- **Driver: psycopg 3 (`psycopg[binary]`), sync, one short-lived connection per request.** Handlers stay sync (FastAPI runs them in its thread pool), like the existing endpoints. A connection per request has no pool state to go stale during an outage, so AC-002.5/AC-002.6 (503 while down, served again as soon as the database is back) hold without reconnect logic; at a task board's load the extra connect (a few ms in-cluster) is cheap. A pool can replace it behind `TaskStore` later without changing the contract. The binary wheel bundles libpq, so the Dockerfile does not change. ADR pending: `cplat adr add postgres-task-storage --decision "Tasks are stored in Postgres through psycopg 3; the service owns its schema and applies it idempotently under an advisory lock, without Alembic"` (this run had no shell to create it).
- **The service owns the schema; no Alembic.** `tasks/schema.py` holds an ordered list of idempotent DDL statements. `TaskStore.ensure_schema()` runs them in one transaction after `SELECT pg_advisory_xact_lock(2002001)`, so two replicas starting together serialise and the second one finds everything in place (the lock is needed: concurrent `CREATE TABLE IF NOT EXISTS` can still fail on the catalog's unique index). It runs once at startup (best effort, a lifespan hook) and again lazily on the first successful connection of a `TaskStore` that has not applied it yet, so a pod that started while the database was down becomes ready once it is back. A later schema change appends statements; it never edits an applied one.
- **Creation order comes from the database**, not the process: `seq bigint GENERATED ALWAYS AS IDENTITY`, and `GET /tasks` orders by `seq` (AC-002.1, AC-002.3). Ids stay `str(uuid.uuid4())` assigned by the service (spec 001 A5), stored in a `uuid` column with a `UNIQUE` constraint, so no two tasks in the environment share an id (AC-002.3).
- **Timeouts per connection:** `connect_timeout=1` and `options="-c statement_timeout=2000"` (readiness: `statement_timeout=1000`). psycopg/libpq enforce a 2 s minimum for `connect_timeout`, so an unreachable host (no RST) costs at most 2 s before the 503; a refused port fails at once. Both stay inside the 3 s of AC-002.5. Departs from the system contract's "connect timeout 1 s": the client library cannot go below 2 s; the 3 s criterion still holds and the website's 2 s timeout treats the slow case as "unavailable" either way.
- **Errors:** the store turns `psycopg.OperationalError` (which includes `QueryCanceled` from the statement timeout), `psycopg.InterfaceError` and a missing `DATABASE_URL` into `StorageUnavailableError`; the router turns that into `503 {"detail": "Task storage is unavailable"}` via `HTTPException`. Other database errors are bugs and stay 500. The insert runs in a transaction, so a failed request stores nothing (AC-002.5).
- **Configuration only from `DATABASE_URL`** (spec note), read when the store is created. Unset or empty: the app still starts, `/health` is 200, `/ready` and the task endpoints answer 503, and one `database_url_missing` error is logged. The DSN is never logged (it holds the password).
- **Titles containing U+0000 get 422 on `title`.** Postgres `text` cannot store a NUL character; without this rule such a title would be a 500. It is the only addition to the 001 validation rules.
- **`TaskStore` keeps its name and interface** (`add`, `list`, `TaskStore()` constructible without arguments, `get_task_store()` singleton). The in-memory implementation is removed (spec note: no in-memory store remains); spec 001's acceptance and unit tests keep working unchanged because the test suite points `DATABASE_URL` at a real Postgres and empties the table before each test.
- **Tests use a real Postgres from devbox** (spec note): `postgresql@16` joins the devbox packages and `pytest-postgresql` starts a throwaway server per test session (no Docker needed, so CI's devbox-only runners work). `TEST_DATABASE_URL`, when set, points the suite at an existing server instead.

## Modules

| Module | Responsibility | New / changed |
|---|---|---|
| `src/taskboard21_api/tasks/schema.py` | `MIGRATIONS: list[str]` (idempotent DDL), `SCHEMA_LOCK_ID = 2002001` | new |
| `src/taskboard21_api/tasks/store.py` | Postgres `TaskStore` (`add`, `list`, `ping`, `ensure_schema`), `StorageUnavailableError`, `get_task_store()` | changed (in-memory store removed) |
| `src/taskboard21_api/tasks/models.py` | reject U+0000 in `title` | changed |
| `src/taskboard21_api/tasks/router.py` | map `StorageUnavailableError` to 503 | changed |
| `src/taskboard21_api/main.py` | `/ready` checks the database through `get_task_store`; lifespan applies the schema at startup | changed |
| `tests/conftest.py` | session Postgres, `DATABASE_URL` for the suite, empty `tasks` before each test | changed |

Signatures:

```python
class StorageUnavailableError(Exception): ...      # message never contains the DSN

class TaskStore:
    def __init__(self, dsn: str | None = None) -> None: ...  # None: os.environ.get("DATABASE_URL", "")
    def add(self, data: TaskCreate) -> Task: ...    # INSERT ... RETURNING; raises StorageUnavailableError
    def list(self) -> list[Task]: ...               # SELECT ... ORDER BY seq; raises StorageUnavailableError
    def ensure_schema(self) -> None: ...            # advisory lock + MIGRATIONS; once per instance; raises StorageUnavailableError
    def ping(self) -> bool: ...                     # ensure_schema() if needed, then SELECT 1 (1 s statement timeout); never raises

@functools.lru_cache(maxsize=1)
def get_task_store() -> TaskStore: ...              # process-wide store over DATABASE_URL
```

Pseudocode of one call:

```python
def list(self) -> list[Task]:
    try:
        with self._connect(statement_timeout_ms=2000) as conn:   # psycopg.connect(dsn, connect_timeout=1, options=...)
            self._ensure_schema_on(conn)                            # no-op after the first success
            rows = conn.execute("SELECT id::text, title, due_date FROM tasks ORDER BY seq").fetchall()
    except (psycopg.OperationalError, psycopg.InterfaceError) as exc:
        logger.warning("task_storage_unavailable", error=type(exc).__name__)
        raise StorageUnavailableError("Task storage is unavailable") from exc
    return [Task(id=r[0], title=r[1], due_date=r[2]) for r in rows]
```

## Contract

The resource contract of spec 001 is unchanged; this spec adds the 503 responses and the database-backed readiness. All bodies are `application/json`.

**`POST /tasks`**: request `{"title": str, "due_date"?: "YYYY-MM-DD" | null}`; unknown fields ignored.

- `201` → `{"id": str, "title": str, "due_date": "YYYY-MM-DD" | null}`; the task is the last element of the next `GET /tasks` on any instance (AC-002.3, AC-002.4).
- `422` → FastAPI's validation body `{"detail": [{"type": str, "loc": ["body", "<field>"], "msg": str, "input": any}]}`, field = last element of `loc`; nothing stored. Rules as in spec 001, plus: a `title` containing U+0000 is rejected on `title`.
- `503` → `{"detail": "Task storage is unavailable"}` within 3 s when the database cannot be reached or a statement times out; nothing stored (AC-002.5).

**`GET /tasks`**:

- `200` → JSON array of every stored task, oldest first by creation, no limit; `[]` when none (AC-002.1, AC-002.2).
- `503` → `{"detail": "Task storage is unavailable"}` within 3 s (AC-002.5).

**`GET /ready`**: `200 {"status": "ready"}` when the schema is applied and `SELECT 1` answers; `503 {"status": "not ready"}` otherwise, including an unset `DATABASE_URL` (AC-002.6). Checks the database on every call, no caching.

**`GET /health`**: unchanged, `200 {"status": "ok"}`, never touches the database.

**Config**: `DATABASE_URL` (libpq URI, e.g. `postgresql://user:pass@host:5432/db`), injected by the system's gitops entry. `PG*` are set too and fill gaps libpq finds in the URI; the service never reads them itself.

## Data

Table `tasks`, created by `MIGRATIONS[0]`:

```sql
CREATE TABLE IF NOT EXISTS tasks (
    seq        bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id         uuid        NOT NULL UNIQUE,
    title      text        NOT NULL,
    due_date   date,
    created_at timestamptz NOT NULL DEFAULT now()
);
```

No data migration: the in-memory tasks of spec 001 are not carried over (they never survived a restart anyway).

## Testing notes

- `tests/conftest.py` provides, for every test: a session-scoped Postgres (pytest-postgresql `postgresql_proc` plus a `DatabaseJanitor`-created database, or `TEST_DATABASE_URL` when set), the session fixture `database_url: str` (its DSN), `os.environ["DATABASE_URL"]` set to it with `get_task_store.cache_clear()`, and an autouse fixture that empties `tasks` (when the table exists) before each test. Acceptance tests may use `database_url` directly.
- **Restart** (AC-002.1, AC-002.2): build a fresh `TaskStore(database_url)` and override `app.dependency_overrides[get_task_store]` with it, or start a new `uvicorn taskboard21_api.main:app` subprocess with `DATABASE_URL` set; both apply the schema again, which must be a no-op.
- **Two instances** (AC-002.3): two `TaskStore(database_url)` objects behind two clients (dependency override per request), or two uvicorn subprocesses on different ports with the same `DATABASE_URL`.
- **Outage** (AC-002.5, AC-002.6): a store over an unreachable DSN, e.g. `TaskStore("postgresql://u:p@127.0.0.1:1/x")`, via the dependency override; `/ready` uses the same `get_task_store` dependency, so the override drives it too. Recovery = override back to `TaskStore(database_url)`: `/ready` is 200 and earlier tasks are listed. Count stored rows through `database_url` to assert "nothing stored".
- Smoke: a read-only `GET /ready` → 200 check keeps readiness covered in staging and prod; writing smoke tests keep `smoke-<uuid>` titles.
