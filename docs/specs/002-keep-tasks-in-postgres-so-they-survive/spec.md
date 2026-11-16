---
spec_id: 002-keep-tasks-in-postgres-so-they-survive
title: Keep tasks in Postgres so they survive restarts and are shared by every instance
status: done
priority: P1
shape: service-python
parent: ika100-demo/taskboard21-gitops:001-persistent-tasks-in-postgres-with-a-web
---

# 002 — Keep tasks in Postgres so they survive restarts and are shared by every instance

## Problem

The Task API keeps tasks in its own memory. Every restart or redeploy loses them, and two running instances each show a different board. People also have no way to use the board except by calling the API directly, because the website has no task features yet. This spec makes tasks durable and shared, stored in a Postgres database, and gives people a web page where they can see the board and add tasks to it.

## System context

Slice of the system plan `001-persistent-tasks-in-postgres-with-a-web` in `ika100-demo/taskboard21-gitops` for `taskboard21-api` (service-python). The system criteria and the contract below are binding: every criterion of this spec implements one of them and names it: `(system AC-<NNN>.<n>)`.

### System criteria

- **AC-001.1** Given a task created through `POST /tasks` or the web page, when the Task API is restarted or redeployed, then `GET /tasks` still returns that task with the same `id`, `title` and `due_date` it had when it was created, in the same position in creation order.
- **AC-001.2** Given the Task API runs as two instances in one environment, when a task is created through one instance, then `GET /tasks` served by either instance includes it, and no two tasks in the environment share an `id`.
- **AC-001.5** Given the start page is open, when a person enters the title "Buy milk", optionally a due date, and submits the form, then within 2 seconds the task appears at the end of the list without a manual page reload, the form is emptied, and `GET /tasks` returns the task with the same title and due date.
- **AC-001.7** Given the Task API cannot reach its database, when a client sends `GET /tasks` or `POST /tasks`, then the response is 503 with a JSON error body, no task is created, and the API's readiness check reports not ready until the database is reachable again; once it is, all tasks created before the outage are listed again.

### Contract

Caller: `taskboard21-web` (server side). Callee: `taskboard21-api`, base URL from `TASK_API_URL` (dev: `http://taskboard21-api`). JSON bodies, `Content-Type: application/json`, no authentication (spec non-goal). The resource contract is unchanged from the Task API's spec 001.

**Task object**

```json
{"id": "<string, server-assigned, unique in the environment>", "title": "<string, as sent>", "due_date": "YYYY-MM-DD" | null}
```

**`GET /tasks`**

- `200` → JSON array of every task in creation order, oldest first, no limit; `[]` when none is stored.
- `503` → `{"detail": "Task storage is unavailable"}` when the database cannot be reached.

**`POST /tasks`** — request `{"title": string, "due_date"?: "YYYY-MM-DD" | null}`; unknown fields ignored.

- `201` → the created task object; it is the last element of the next `GET /tasks`.
- `422` → FastAPI validation body `{"detail": [{"loc": ["body", "<field>"], "msg": "...", "type": "...", "input": ...}]}`; the field is the last element of `loc`. Title rule: 1 to 200 characters, not only whitespace; `due_date` must be a real calendar date. Nothing is stored.
- `503` → `{"detail": "Task storage is unavailable"}`; nothing is stored.

**`GET /ready`** (probe, not called by the website) — `200 {"status": "ready"}` when the database answers, else `503 {"status": "not ready"}`. `GET /health` stays `200` during a database outage, so pods are not restarted for it.

**Website rendering rules** — `due_date` shown verbatim as `YYYY-MM-DD`, `null` shown as "No due date"; list order is the API's order; the website does not re-sort.

### Errors

- Error bodies are JSON with a `detail` key: a string for `503`, FastAPI's array of `{loc, msg, type, input}` for `422`.
- The website validates the title before sending (same rule as the API), so a `422` is not expected; if one arrives for `title`, it shows "Title is required" (empty or whitespace) or "Title must be at most 200 characters" (over 200) next to the title field and keeps the input; a `422` for any other field is treated like an unlisted response.
- Any status or body the contract does not list (including `5xx`, a non-JSON body, a connection error, and a `200` that is not a JSON array) is treated as "API unavailable": the website shows "Tasks are unavailable right now. Please try again later." (instead of the list on load, above the form on submit), keeps the form's input, and its own page still returns `200`. It logs one line with the status or error, never the title.
- No retries: `POST /tasks` is not idempotent, and a retried `GET` would push the page past its time budget.

### Timeouts

- Website → `GET /tasks` (page render): 2 s total; on timeout, the unavailable state above.
- Website → `POST /tasks` (submit): 2 s total; on timeout, the unavailable state above the form, input kept. The website does not know whether the task was stored; a reload shows the truth.
- Task API → Postgres: connect timeout 1 s and statement timeout 2 s per request; when either is hit or the connection fails, the request answers `503` (well within the 3 s of the API criterion). `GET /ready` checks the database with a 1 s budget.
- When the database is down, readiness fails and Kubernetes takes the API pods out of the Service; the website then gets connection errors instead of `503`, which it treats the same way. Once the database is back, readiness passes and the stored tasks are served again.

### Provided by the system

The gitops part of this plan wires these for this repo; rely on them, do not ask for them again:

- resource `postgres`: env `DATABASE_URL`, `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`
- replicas `2` in `dev`

### Notes for this repo

Connection comes only from DATABASE_URL (PG* also set) injected by the gitops entry; no in-memory store remains in the
deployed service. The API owns the schema: create/migrate it idempotently at startup so two replicas starting together
are safe. Creation order must hold across instances (a database-assigned sequence or timestamp, not process state).
Ids stay server-assigned strings (uuid4 is fine). Tests need a real Postgres (e.g. a test container or a devbox service).

## Stories

<!-- As a <persona>, I want <goal>, so that <benefit>. -->

## Acceptance criteria

- **AC-002.1** Given tasks A, B and C were created through POST /tasks, when the service is restarted against the same database, then GET /tasks returns 200 with A, B and C first-to-last in creation order, each with the same id, title and due_date that POST /tasks returned (system AC-001.1)
- **AC-002.2** Given no task is stored in the database, when a client sends GET /tasks, then the response is 200 with an empty JSON array, also right after a restart (system AC-001.1) (replaces AC-001.6)
- **AC-002.3** Given two service instances use the same database, when a task is created through POST /tasks on one of them, then GET /tasks on either instance includes it at the end of the list, and no two tasks returned share an id (system AC-001.2)
- **AC-002.4** Given the database is reachable, when a client sends POST /tasks with {"title": "Buy milk", "due_date": "2026-12-01"} or with only a title, then the response is 201 with id, title and due_date (null when omitted) as before, and the next GET /tasks returns that task with the same fields; invalid input still gets 422 naming the field and stores nothing (system AC-001.5)
- **AC-002.5** Given the database cannot be reached, when a client sends GET /tasks or POST /tasks, then the response is 503 with the JSON body {"detail": "Task storage is unavailable"} within 3 seconds and no task is stored (system AC-001.7)
- **AC-002.6** Given the database cannot be reached, when the readiness probe calls GET /ready, then it answers 503 {"status": "not ready"}; when the database is reachable again, GET /ready answers 200 {"status": "ready"} and GET /tasks lists every task created before the outage (system AC-001.7)

## Non-goals

## Assumptions

<!-- Spec 149: decisions taken by default, approved with the spec. One bullet each: - **A1** <the decision> (other option: <…>; affects AC-…). A revised one is struck through (~~…~~), never deleted. -->

## Open questions

<!-- Only what may not be decided by default (spec 149): security or access, money, destroying or migrating data, or a request too ambiguous to build. Approval is refused while any is open. Strike answered ones (~~…~~) and fold the answer into the criteria. -->

## Changelog

- 2026-11-16 created from the system plan, with its criteria (spec 147)
- 2026-11-16 approved
- 2026-11-16 building
- 2026-11-16 done
