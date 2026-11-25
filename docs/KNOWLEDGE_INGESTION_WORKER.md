# Durable knowledge-ingestion worker

Document uploads and reindex requests create an `ingestion_jobs` row in the same database transaction as the document state. The API no longer performs indexing in a request-bound `BackgroundTasks` callback.

Start one worker from `apps/api` with:

```powershell
.\.venv\Scripts\python.exe -m app.scripts.knowledge_worker
```

The worker claims queued jobs with PostgreSQL `FOR UPDATE SKIP LOCKED`, leases each claim for 60 seconds, and records a heartbeat. Expired leases are eligible for recovery. Definitive failures retry with bounded exponential backoff up to three attempts, then become `failed` with a sanitized message. Successful jobs become `succeeded` after the document reaches `ready`.

Inspect a document job through the organization-scoped endpoint:

```text
GET /api/v1/organizations/{organization_id}/documents/{document_id}/job
```

The endpoint returns status, attempts, timestamps, and safe failure text only. It does not return document contents, provider credentials, or embedding payloads.

Runtime multi-worker, crash/restart, and tenant-isolation verification requires the disposable PostgreSQL environment; it must not be run against staging.
