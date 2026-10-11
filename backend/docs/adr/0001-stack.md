# ADR-0001: Backend stack

**Status:** Accepted (2026-10-04)

## Context
The repository contained only an unrelated C# console exercise with no domain
code, no database and no build toolchain available in the target environment.
There was therefore no architecture to reuse.

## Decision
Python 3.11 with FastAPI (OpenAPI out of the box), Pydantic v2 (schema
validation for every AI-generated or imported structured value), SQLAlchemy 2 +
Alembic (SQLite for dev/tests, PostgreSQL-compatible for production), structlog,
and Google OR-Tools CP-SAT for optimization.

## Consequences
- The whole backend is testable in-process (pytest, hypothesis).
- The C# project is left untouched; it is not part of the product.
- A separate frontend can consume the OpenAPI document.
