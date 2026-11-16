# Design — 001 Create and list tasks in memory

## Decisions

- Tasks live in a process-local `TaskStore` (a list guarded by a `threading.Lock`), reached through the FastAPI dependency `get_task_store()`. FastAPI runs sync endpoints in a thread pool, so the lock keeps concurrent appends safe; the dependency is the seam the later durable-storage spec replaces, and it lets in-process tests swap in a fresh store. Feature-local, no ADR: the store is temporary by the spec's own non-goals.
- Validation stays in Pydantic models so errors use FastAPI's standard 422 body (A6); no custom exception handler.
- `title` is a `StrictStr` with a validator: reject when `len(title) > 200` or `title.strip() == ""`; the value is stored exactly as sent (A4). The length limit counts the raw string.
- `due_date` uses a `mode="before"` validator: `None` passes (A8); otherwise the value must be a `str` matching `^\d{4}-\d{2}-\d{2}$` and parse with `date.fromisoformat`. Pydantic's own `date` parsing would also accept integers (Unix timestamps) and datetime strings, which AC-001.4 rules out. Past dates are accepted (A3).
- `id` is `str(uuid.uuid4())`, assigned by the store (A5). Unknown request fields, including a client-sent `id`, are ignored (Pydantic default `extra="ignore"`).
- One structured log line per created task (`event="task_created"`, `task_id`); the title is not logged.

## Modules

| Module | Responsibility | New / changed |
|---|---|---|
| `src/taskboard21_api/tasks/__init__.py` | package marker (docstring only) | new |
| `src/taskboard21_api/tasks/models.py` | `TaskCreate` (request, validation), `Task` (response) | new |
| `src/taskboard21_api/tasks/store.py` | `TaskStore` (`add`, `list`), `get_task_store()` singleton dependency | new |
| `src/taskboard21_api/tasks/router.py` | `APIRouter` with `POST /tasks`, `GET /tasks` | new |
| `src/taskboard21_api/main.py` | `app.include_router(tasks_router)` | changed |

Signatures:

```python
class TaskCreate(BaseModel):
    title: StrictStr                 # validated: 1..200 chars, not whitespace-only
    due_date: date | None = None     # validated before: None or "YYYY-MM-DD" string, real calendar date

class Task(BaseModel):
    id: str
    title: str
    due_date: date | None            # serialised as "YYYY-MM-DD" or null

class TaskStore:
    def add(self, data: TaskCreate) -> Task: ...   # assigns uuid4 id, appends under lock
    def list(self) -> list[Task]: ...              # copy, in insertion order

def get_task_store() -> TaskStore: ...             # returns the module-level singleton
```

## Contract

All bodies are `application/json`. No authentication (spec non-goal).

**`POST /tasks`**: request `{"title": str, "due_date"?: "YYYY-MM-DD" | null}`; other fields are ignored.

- `201` → `{"id": str, "title": str, "due_date": "YYYY-MM-DD" | null}` (AC-001.1, AC-001.2). `title` is returned exactly as sent; `due_date` is `null` when omitted or sent as `null`.
- `422` → FastAPI's standard validation body; no task is stored (AC-001.3, AC-001.4):

  ```json
  {"detail": [{"type": "<pydantic error type>", "loc": ["body", "title"], "msg": "<text>", "input": <value>}]}
  ```

  The offending field is the last element of `loc` (`"title"` or `"due_date"`). Tests assert on `loc`, not on `type` or `msg`. Cases: `title` missing, not a string (e.g. `123`, `null`), `""`, whitespace-only, more than 200 characters; `due_date` not a string, not `YYYY-MM-DD` (e.g. `"tomorrow"`, `"2026-12-01T00:00:00"`), or not a calendar date (`"2026-02-30"`). A body that is not a JSON object also gets `422` with `loc` `["body"]`.

**`GET /tasks`**: `200` → JSON array of task objects as above, in creation order, no limit (AC-001.5, AC-001.6, AC-001.7). Empty store → `[]`.

## Testing notes

- In-process acceptance tests isolate state by overriding the dependency: `app.dependency_overrides[get_task_store] = lambda: store` with a fresh `TaskStore()` per test (import from `taskboard21_api.tasks.store`), and clear the override afterwards. AC-001.6 relies on this.
- Smoke tests (AC-001.1, AC-001.2, AC-001.5) run against a shared instance: they are `@pytest.mark.smoke` + `@pytest.mark.writes`, use titles `smoke-<uuid>`, and for AC-001.5 assert that their own three tasks appear in the list in creation order (other tasks may be present). A read-only smoke check `GET /tasks` → `200` with a JSON array keeps the endpoint checked in staging and prod.

## Data

None persisted. Each instance holds its own tasks in memory; they are lost on restart (spec non-goal).
