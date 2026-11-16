---
spec_id: 001-create-and-list-tasks-in-memory
shape: service-python
spec_hash: 4bd4f340c014
summary: In-memory POST /tasks and GET /tasks with title and optional due date
tasks:
  - id: t1
    title: Add task models with validation and the in-memory TaskStore
    files: [src/taskboard21_api/tasks/__init__.py, src/taskboard21_api/tasks/models.py, src/taskboard21_api/tasks/store.py, tests/test_task_store.py]
    covers: [AC-001.3, AC-001.4, AC-001.5, AC-001.6, AC-001.7]
    parallel_safe: true
    depends_on: []
    done: true
  - id: t2
    title: Expose POST /tasks and GET /tasks and wire the router into the app
    files: [src/taskboard21_api/tasks/router.py, src/taskboard21_api/main.py]
    covers: [AC-001.1, AC-001.2, AC-001.3, AC-001.4, AC-001.5, AC-001.6, AC-001.7]
    parallel_safe: true
    depends_on: [t1]
    done: true
---

# Plan — 001 Create and list tasks in memory

Contract and decisions: [design.md](design.md).

## t1 — Add task models with validation and the in-memory TaskStore

**Files:** src/taskboard21_api/tasks/__init__.py, src/taskboard21_api/tasks/models.py, src/taskboard21_api/tasks/store.py, tests/test_task_store.py
**Covers:** AC-001.3, AC-001.4, AC-001.5, AC-001.6, AC-001.7
**Goal:** the domain layer of the feature: request/response models that reject every invalid title and due date named in the spec, and a thread-safe store that assigns unique ids and keeps creation order.

**Implementation notes:**
- `tasks/__init__.py`: package docstring only (no re-exports, so it imports cleanly before the router exists).
- `models.py`: `TaskCreate` with `title: StrictStr` and `due_date: date | None = None`; `field_validator("title")` raises `ValueError` when `len(v) > 200` or `not v.strip()`; returns `v` unchanged (A4).
- `field_validator("due_date", mode="before")`: `None` passes; a non-`str` or a string not matching `^\d{4}-\d{2}-\d{2}$` raises `ValueError`; then `date.fromisoformat(v)` (its `ValueError` covers "2026-02-30").
- `Task` response model: `id: str`, `title: str`, `due_date: date | None`.
- `store.py`: `TaskStore` holds `list[Task]` and a `threading.Lock`; `add(data)` builds `Task(id=str(uuid.uuid4()), ...)`, appends under the lock, logs `task_created` with `task_id` via structlog, returns the task; `list()` returns a copy under the lock.
- Module-level `_store = TaskStore()` and `def get_task_store() -> TaskStore: return _store`.
- `tests/test_task_store.py`: unit tests for the validators (each invalid case of AC-001.3/AC-001.4, past date accepted, explicit `null`) and the store (order, distinct ids for equal titles, empty start).

**Done when:** `tests/test_task_store.py` passes and `devbox run quality` is green. The HTTP acceptance tests need t2.

## t2 — Expose POST /tasks and GET /tasks and wire the router into the app

**Files:** src/taskboard21_api/tasks/router.py, src/taskboard21_api/main.py
**Covers:** AC-001.1, AC-001.2, AC-001.3, AC-001.4, AC-001.5, AC-001.6, AC-001.7
**Goal:** the HTTP contract from design.md on top of t1's models and store.

**Implementation notes:**
- `router.py`: `router = APIRouter(tags=["tasks"])`.
- `@router.post("/tasks", status_code=201, response_model=Task)` taking `body: TaskCreate` and `store: TaskStore = Depends(get_task_store)`; returns `store.add(body)`.
- `@router.get("/tasks", response_model=list[Task])` returning `store.list()`.
- Sync handlers (`def`), matching the existing endpoints in `main.py`.
- `main.py`: `from .tasks.router import router as tasks_router` and `app.include_router(tasks_router)` after the middleware setup; leave health, ready, ping and metrics unchanged.
- No custom exception handler: FastAPI's default 422 body is the contract.

**Done when:** all acceptance tests for AC-001.1 to AC-001.7 pass, and `devbox run ci` is green (coverage gate included).
