# 01. Storage retention backup and disaster recovery policy

Permanent purge is disabled. The normal retention worker cannot remove chat,
files, database rows, object-storage objects, or backups.

## Recovery units

The database and private object storage are one recovery pair:

1. Capture a PostgreSQL dump with `backend/scripts/backup_postgres.sh`.
2. Capture the MinIO data volume with `backend/scripts/backup_minio.sh`.
3. Keep the matching UTC timestamp, checksum, migration revision, and service
   image in the backup metadata.
4. Restore PostgreSQL before starting application workers, then restore the
   matching MinIO volume and verify tenant prefixes.
5. Run Alembic only to the revision included in the application image.
6. Run storage reconciliation in dry-run/read-only mode before re-enabling
   writes.

The database backup contains lifecycle identity, reservation, archive-manifest,
and reconciliation metadata. It does not make secrets or private content
public; backup access must use the existing encrypted backup and operator
access controls.

## Verification status

The recorded local proof created PostgreSQL and MinIO backups, verified both checksums,
restored PostgreSQL into a disposable database, and validated 83 restored
public tables. It restored the MinIO archive into an isolated temporary volume
containing 150 files and verified the isolated MinIO health endpoint with HTTP
200. Disposable targets were removed after verification; the active database
and object-store volume were never overwritten. That restore snapshot used
migration head `20260928_0001`; it is not the current source head or a statement
about the current local database. The source and deployment status is tracked
in the [current worktree and release index](../release/03-current-worktree-change-index.md).
This historical local evidence does not establish that the VPS or an external
staging environment has completed a restore drill.

The local staging profile also opts into metadata-only automatic archive for
proof. The worker archives only reconciled, known user-content categories;
provider/security/audit/unknown categories and any tenant with reconciliation
drift remain protected. Production/VPS keeps this flag disabled until the
external restore drill and release gate are complete.

## Required operational targets

Production must set and record an approved RPO/RTO for each environment. The
repository does not invent those values. Until an operator approves them, the
safe release gate is: daily database/object-store backups, checksum
verification, and a quarterly staging restore drill.

## Restore verification checklist

- Verify both checksums before restore.
- Verify PostgreSQL and object storage belong to the same backup timestamp.
- Verify Alembic revision before starting workers.
- Verify tenant isolation and object-prefix checks with two staging tenants.
- Verify an archived lifecycle item can be restored without changing source
  content.
- Verify active DeepSpace runs, queues, approvals, and provider credentials
  remain present.
- Run reconciliation and investigate mismatches before production traffic.
- Keep the previous application image available for rollback.

No restore process calls a permanent purge operation. A failed or partial
restore stops writes and is escalated; it is never “repaired” by deleting
unknown rows or objects.
