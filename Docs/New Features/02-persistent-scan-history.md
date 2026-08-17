# Persistent Malware Scan History

## What to do

Persist every security decision: engine, engine version, scan timestamp, result, reason, checksum,
and request/job correlation ID.

## Why to do it

ClamAV currently protects uploads, but operators need durable evidence for investigations, rescans,
compliance, and customer support.

## Already have

- Real ClamAV INSTREAM scanning in `malware_scan_service.py`.
- Fail-closed production behavior and readiness checks.
- Document SHA-256 and audit logging helpers.

## Where and how

| Layer | Proposed location / contract |
|---|---|
| Model | `DocumentScanRecord` in `backend/app/ingestion/models/scan_record.py` |
| API | `GET /documents/{id}/security/scans`, admin `POST /documents/{id}/security/rescan` |
| Service | `backend/app/ingestion/services/security/scan_history_service.py` |
| UI | Security panel in `DocumentDetailClient.tsx`; admin scan-history table |
| Audit | `documents.security_scan.completed`, `.failed`, `.rescan_requested` |
| Tests | Clean, infected, unavailable scanner, retry, ownership, audit completeness |

## Safety rules

Store result metadata, never file contents or scanner secrets. A rescan creates an immutable new
record. Download and query remain blocked while a required rescan is pending or failed.

## Must not break

Existing uploads still fail closed when required ClamAV is unavailable. Historical records are
backfilled as `legacy_unknown`, never falsely marked clean.
