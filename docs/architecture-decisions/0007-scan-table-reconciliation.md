# ADR 0007: Evolve Prompt 01 scan tables in place

- Status: Accepted
- Date: 2026-11-14

## Context

Prompt 01 already stores live scan jobs in `inspection_jobs` and immutable scanner
evidence in `scan_results`. Prompt 04 introduces tenant-aware `ScanJob` and
`ScanResult` entities with UUID primary keys. Creating replacement tables or copying
only normalized data would risk evidence loss and break the Celery worker.

## Decision

Migration `0002` evolves both tables in place:

- the ORM entity `ScanJob` maps to `inspection_jobs`, with `InspectionJob` retained as
  a compatibility alias for the API and worker;
- valid UUID strings in `inspection_jobs.id` and `scan_results.job_id` are converted to
  native PostgreSQL UUID columns while preserving the foreign-key relationship;
- the old integer `scan_results.id` becomes unique `legacy_id`;
- a generated UUID becomes the new `scan_results.id` primary key;
- nullable organization, project, and repository references are added so legacy rows
  remain valid and new tenant-aware scans can be scoped;
- timestamps, correlation IDs, idempotency keys, foreign keys, uniqueness constraints,
  and filter indexes are added without replacing raw or normalized evidence.

Legacy scan rows remain unassigned to an organization until an explicit administrative
adoption workflow is designed. Existing Prompt 01 routes and worker execution continue
to use the same physical tables.

Downgrade removes only Prompt 04 entities and columns, restores UUID job identifiers to
36-character strings, removes the generated result UUID, renames `legacy_id` back to
`id`, and restores it as the integer primary key. Migration tests insert Prompt 01 data,
upgrade, downgrade, and upgrade again while checking the same job and provenance.
Before restoring Prompt 01's shorter state columns, downgrade maps `pending` to
`queued`, `cancelled`/`timed_out` to `failed`, `partially_completed` to `completed`,
and repository sources to the legacy `archive` source class.

## Consequences

- No scanner evidence is dropped or regenerated.
- PostgreSQL is required; UUID conversion intentionally does not support SQLite.
- Tenant-aware APIs must not expose nullable legacy rows. The backward-compatible
  Prompt 01 job routes remain the only unscoped legacy surface until a later adoption
  migration.
- Downgrade is reversible for every row originating in Prompt 01 because `legacy_id`
  remains unique.
