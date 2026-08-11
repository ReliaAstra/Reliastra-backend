# ADR-001: FastAPI and SQLAlchemy 2 async

**Status:** Accepted

FastAPI supplies versioned REST routing, Pydantic v2 validation, OpenAPI, and native coroutine handlers. SQLAlchemy 2 with asyncpg keeps database waits off the event loop and preserves a mature migration path through Alembic. Sessions are request/task scoped and injected; no handler performs synchronous ORM work.
