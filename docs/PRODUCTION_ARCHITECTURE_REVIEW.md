# Production architecture review

The first hosted release should support personal CAD projects and shared
projects through one tenant boundary. This review proposes the contract for
that release and the migration from the current local installation.

## Existing transition points

- `bigbrain/web/server.py` wires HTTP and realtime entry points.
- `bigbrain/web/sessions.py` and `bigbrain/web/run_history.py` resolve
  conversations and execution history.
- `bigbrain/web/cad_api.py`, `bigbrain/web/evidence_api.py` and
  `bigbrain/web/attachments.py` expose document and evidence resources.
- `bigbrain/cad_store.py` stores local document revisions and owner metadata.
- `bigbrain/auth/registry.py` manages inference providers. Product identity
  needs an independent user session and membership lookup.

Confirm the route and storage inventory against the checkout before migration.
Use hosted database records for identities, memberships, run metadata and
revision references. Use private object storage for model bytes and evidence.
Keep local filesystem adapters for desktop and development.

## Access model

| Action | Viewer | Editor | Owner |
| --- | --- | --- | --- |
| Read project, run history and evidence | Yes | Yes | Yes |
| Download model and attachments | Tenant policy | Tenant policy | Tenant policy |
| Modify document, attach inputs and start or stop runs | | Yes | Yes |
| Manage membership and project deletion | | | Yes |
| Manage subscription and quotas | | | Yes |

Membership revocation must take effect on new HTTP requests, existing event
subscriptions and subsequent commands from queued jobs. Service workers use
explicit tenant-scoped job identities. Platform administration is a separate
role. Support access to content requires a time-limited grant linked to a case
and recorded in the audit trail. Routine support uses redacted metadata.

## Runs, delivery and accounting

A run carries tenant, actor, project and base revision. Admission reserves
usage idempotently. Results publish only after document ownership and base
revision are checked again. Reconnect cursors, cache keys and export links
are tenant-scoped. URLs are short-lived and issuance requires an authorized
request. Use per-tenant worker concurrency and queue limits.

The admin dashboard needs account and membership lifecycle, run diagnostics,
usage reservations and settlements, incidents, and audited support grants.
Pricing, credit policy and payment implementation belong to the next review.

## Migration rehearsal

Export one disposable local project with conversation, executions, CAD
history, attachments and evidence. Import it into a personal tenant using
a manifest and content hashes. Verify the same document can be reopened, that
its checks resolve to the original source, and that repeating the import
preserves identity. Keep the exported source until verification and rollback
are exercised. Define retention, deletion and backup recovery windows before
accepting customer data.

## Acceptance cases

- A second tenant cannot retrieve any project, event, attachment, export,
  revision or check from the imported tenant, including through guessed IDs.
- Revocation closes an active subscription and stops further commands from a
  queued run. A concurrent worker cannot publish after losing revision ownership.
- Retrying admission or completion creates one chargeable run record.
- Support grant expiry and every protected read appear in the audit trail.
- Restore from a disposable backup, reconcile object hashes and demonstrate
  the account deletion policy. Exercise the local import adapter on Linux
  and Windows.

Review decisions are identity provider, project sharing and export defaults,
support access policy, data jurisdiction and retention, and the first
deployment topology. Implementation starts after the architecture review.
