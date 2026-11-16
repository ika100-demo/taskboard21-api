# ADR-001: Postgres task storage

**Status:** Proposed (2026-11-16)

## Context

<!-- why a decision is needed: the forces and constraints -->

## Decision

Tasks are stored in Postgres through psycopg 3; the service owns its schema and applies it idempotently under an advisory lock, without Alembic

## Consequences

<!-- what becomes easier or harder, what a later change must keep -->
