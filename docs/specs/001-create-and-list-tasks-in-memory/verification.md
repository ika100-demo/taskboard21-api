# Verification — 001 Create and list tasks in memory

**Result:** pass
**Commit:** 5467c17 · **Base:** 2542789 · **Trace:** 7/7 criteria named by tests (smoke: AC-001.1, AC-001.2, AC-001.5)

| Criterion | Verdict | Tests | Implementation | Notes |
|---|---|---|---|---|
| AC-001.1 | met | `tests/test_tasks_api.py::test_create_task_with_due_date`, `tests/test_smoke_tasks.py::test_smoke_ac_001_1_create_task_with_due_date` | `src/taskboard21_api/tasks/router.py:13`, `src/taskboard21_api/tasks/store.py:24`, `src/taskboard21_api/main.py:27` | asserts 201, `id` non-empty string, `title` "Buy milk", `due_date` "2026-12-01" |
| AC-001.2 | met | `tests/test_tasks_api.py::test_create_task_without_due_date_is_null`, `tests/test_smoke_tasks.py::test_smoke_ac_001_2_create_task_without_due_date` | `src/taskboard21_api/tasks/models.py:19`, `src/taskboard21_api/tasks/models.py:34` | asserts 201 and `due_date is None` |
| AC-001.3 | met | `tests/test_tasks_api.py::test_invalid_title_rejected` (missing, int, null, empty, whitespace, too-long), `::test_title_of_200_chars_accepted` | `src/taskboard21_api/tasks/models.py:18`, `src/taskboard21_api/tasks/models.py:23-28` | asserts 422, every error `loc` ends in `title`, list stays `[]`; 200-char boundary accepted |
| AC-001.4 | met | `tests/test_tasks_api.py::test_invalid_due_date_rejected` ("2026-02-30", "tomorrow", datetime string, number) | `src/taskboard21_api/tasks/models.py:30-37` | asserts 422, every `loc` ends in `due_date`, list stays `[]` |
| AC-001.5 | met | `tests/test_tasks_api.py::test_list_returns_tasks_in_creation_order`, `tests/test_smoke_tasks.py::test_smoke_ac_001_5_list_in_creation_order`, `::test_smoke_ac_001_5_list_tasks_is_readable` | `src/taskboard21_api/tasks/router.py:19-22`, `src/taskboard21_api/tasks/store.py:30-33` | asserts 200 and listing equals the three create responses in order A, B, C; smoke filters to its own tasks per design |
| AC-001.6 | met | `tests/test_tasks_api.py::test_list_empty_initially` | `src/taskboard21_api/tasks/store.py:18-20`, `src/taskboard21_api/tasks/store.py:39` | fresh store via dependency override stands in for "since start" (design.md testing notes); asserts 200 and `[]` |
| AC-001.7 | met | `tests/test_tasks_api.py::test_same_title_tasks_get_distinct_ids` | `src/taskboard21_api/tasks/store.py:24` | asserts both listed (len 2, id set matches) and ids differ |

## Non-goals

No durable storage, no single-task read/update/delete, no filtering/sorting/pagination, no extra fields, no authentication. No template-owned layout changed; `main.py` only adds the router include (health, ready, ping, metrics unchanged). ✔

## Deviations from the plan

- `tests/test_tasks_api.py`, `tests/test_smoke_tasks.py` are in no task's `files`: acceptance tests written in the red phase before the plan's tasks; acceptable.
- `spec.md` changed (status `building`, changelog line): pipeline bookkeeping; acceptable.
- `src/taskboard21_api/tasks/router.py:14,20` carry `# noqa: B008` for `Depends(...)` defaults: standard FastAPI idiom, in source not acceptance tests; acceptable.
- Both tasks t1, t2 are `done: true`.

## Contract

Matches `design.md`: `POST /tasks` 201 `{id, title, due_date}`, 422 FastAPI standard body with field in `loc`, `GET /tasks` 200 array in creation order. ✔

## Mutation check (report only)

14 of 15 mutants of the changed code were caught by the acceptance tests (93 %; spec 152, report only).

Survived (a test that names the criterion would fail if it checked this):
- `src/taskboard21_api/tasks/store.py:41 return value → None`
