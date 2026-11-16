---
spec_id: 001-create-and-list-tasks-in-memory
title: Create and list tasks in memory
status: done
priority: P1
shape: service-python
---

# 001 — Create and list tasks in memory

## Problem

The Task API serves only health, readiness, ping and metrics today, so a client has nowhere to record a task or read it back. This first feature gives clients the core of a task board: create a task with a title and an optional due date, and list all tasks. Tasks live in the service's memory only, which keeps the first slice small and lets clients start building against the API now; durable storage comes later.

## Stories

As an API client, I want to create a task with a title and an optional due date, so that I can record work to be done.

As an API client, I want to list all tasks, so that I can show the board.

## Acceptance criteria

- **AC-001.1** Given the service is running, when a client sends `POST /tasks` with `{"title": "Buy milk", "due_date": "2026-12-01"}`, then the response is 201 with a JSON body holding `id`, `title` "Buy milk" and `due_date` "2026-12-01". (smoke)
- **AC-001.2** Given the service is running, when a client sends `POST /tasks` with only `{"title": "Buy milk"}`, then the response is 201 and the body's `due_date` is `null`. (smoke)
- **AC-001.3** Given the service is running, when a client sends `POST /tasks` with the title missing, not a string, empty, only whitespace, or longer than 200 characters, then the response is 422 with an error body naming the field `title`, and no task is created.
- **AC-001.4** Given the service is running, when a client sends `POST /tasks` with a `due_date` that is not a valid calendar date in `YYYY-MM-DD` form (for example "2026-02-30" or "tomorrow"), then the response is 422 with an error body naming the field `due_date`, and no task is created.
- **AC-001.5** Given tasks were created in the order A, B, C, when a client sends `GET /tasks`, then the response is 200 with a JSON array of the three tasks in creation order, each with `id`, `title` and `due_date` exactly as returned when it was created. (smoke)
- ~~**AC-001.6**~~ superseded by AC-002.2 on 2026-11-16: Given no task has been created since the service started, when a client sends `GET /tasks`, then the response is 200 with an empty JSON array.
- **AC-001.7** Given two tasks created with the same title, when a client lists tasks, then both appear, each with its own distinct `id`.

## Non-goals

- Durable storage: tasks are lost when the service restarts, and each running instance holds its own tasks.
- Reading, updating, completing or deleting a single task.
- Filtering, sorting options, search and pagination of the list.
- Fields beyond title and due date (description, status, assignee, time of day, time zone).
- Users, ownership and authentication: anyone who can reach the service may create and list tasks; authentication comes in a later spec.

## Assumptions

- **A1** Endpoints are `POST /tasks` and `GET /tasks` with JSON field names `id`, `title`, `due_date` (other option: `/api/v1/tasks`, camelCase `dueDate`; affects AC-001.1, AC-001.2, AC-001.5).
- **A2** `due_date` is a calendar date `YYYY-MM-DD` without time or time zone (other option: full ISO 8601 timestamp; affects AC-001.1, AC-001.4).
- **A3** Dates in the past are accepted (other option: reject with 422; affects AC-001.4).
- **A4** Title is 1 to 200 characters after ignoring surrounding whitespace for the emptiness check, stored as sent (other option: trim before storing, or another limit; affects AC-001.3).
- **A5** `id` is a server-assigned string, unique within the running instance; clients cannot set it, and unknown request fields are ignored (other option: integer ids from 1, or reject unknown fields; affects AC-001.1, AC-001.7).
- **A6** Validation errors use status 422 with the framework's standard error body that names the offending field (other option: 400 with a custom error shape; affects AC-001.3, AC-001.4).
- **A7** The list returns all tasks in creation order with no limit (other option: newest first, or a page size cap; affects AC-001.5).
- **A8** An explicit `"due_date": null` is treated like an omitted due date (other option: reject with 422; affects AC-001.2).

## Open questions

- ~~May anyone who can reach the service create and list tasks, with no authentication in this spec? (suggested: yes, no auth until a later spec; affects AC-001.1, AC-001.5)~~ Answered 2026-11-16: yes, no authentication for now; authentication comes in a later spec (see Non-goals).

## Changelog

- 2026-11-16 created
- 2026-11-16 amended: open question on authentication answered (no authentication for now, later spec); recorded as a non-goal, criteria unchanged
- 2026-11-16 approved
- 2026-11-16 building
- 2026-11-16 done
- 2026-11-16 AC-001.6 superseded by AC-002.2
