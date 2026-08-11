# ADR-002: Celery for distributed checks

**Status:** Accepted

Checks, evidence, and notifications need independent scaling, retries, delayed execution, and delivery acknowledgement. Celery and Beat provide these capabilities without rebuilding a durable queue on raw asyncio. Beat only claims schedules; workers execute network checks. Queue names isolate check, evidence, and notification capacity.
