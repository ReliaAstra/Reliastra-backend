# ADR-003: Native monthly check-result partitions

**Status:** Accepted

`check_results` is partitioned by monthly ranges of `executed_at`, with a default safety partition. This keeps recent scans and retention operations bounded and leaves a later TimescaleDB/ClickHouse migration behind the repository boundary.

PostgreSQL requires a partitioned table's unique/primary constraint to include its partition key. The physical primary key is therefore `(id, executed_at)`, while `id` remains the API identifier. This is the one intentional physical refinement to the logical model's “UUID PK” shorthand. The migration creates 2025–2031 partitions; operations must provision future partitions ahead of time and move default-partition rows during maintenance.
