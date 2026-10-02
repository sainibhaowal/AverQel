# Archived retention planning documents

These four documents preserve the historical decisions, implementation plan,
decision gates, and complete specification that led to the current Storage
retention design.

They are not the active runtime source of truth. Use the current production
documentation in [`backend/docs/README.md`](../../README.md),
especially the Storage and release sections.

The documents remain archived for review, audit context, and rollback history.
They do not affect application behavior. All four are historical companions;
the backend Storage guide remains authoritative for current behavior, routes,
migrations, schedules, and release gates.

Current implementation status is intentionally explicit in each file:

- local archive-first metadata lifecycle is implemented;
- automatic archive is guarded to development, test, and staging;
- production/VPS automatic archive still requires external staging evidence;
- permanent purge is disabled.
