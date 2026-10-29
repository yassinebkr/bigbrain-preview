# Local project boundaries

Implementation boundaries, 29 October 2026.

## Access inventory

| Boundary | Current implementation | Enforcement |
| --- | --- | --- |
| UI filesystem and selection | `web/local_projects_api.py`, `local_projects.py` | Loopback/origin checks, chooser tickets, project ID and revision |
| Python maintenance | `brains/python_brain.py`, `local_project_maintenance.py` | Shared repair engine, broker and isolated runner |
| Web maintenance and preview | `brains/web_app_brain.py`, `local_project_web.py`, `local_project_preview.py` | Bound scratch, isolated builds and expiring browser leases |
| Verification subprocesses | `local_project_runner.py`, `local_project_checks.py`, `verification/web_gate.py` | Project runtime, output/time limits, process cleanup |
| Recovery | `local_project_recovery.py`, `project_transaction.py`, `project_file_io.py` | Hashes, identity and scoped crash journal |
| Manual recovery release | `local_project_retention.py`, `native_publication.py` | Deletion grant, versioned inventory, separate confirmation, native exclusivity and resumable receipts |
| Provider transport | `local_project_provider.py`, `local_project_transmission.py` | Approved recipient and versioned source inventory |
| Conversation context | `front/front_brain.py`, registry selection and run metadata | Project identity persists with its conversation and result |

## Registry and requests

Store registry metadata outside attached source trees. Each record contains a
UUID, canonical root, root device/inode identity, display name, origin, access
revision and grants for read, write, execute, delete, install, network and provider
transmission. Default attachment grants read access. Changes increment revision.
Operations carry project ID and expected revision; stale requests fail explicitly.
Unavailable or replaced roots require reconciliation through the local chooser.

## Source transmission decision

The specialist adapter requires a concrete transmission contract before
activation. Approved fields:

| Field | Enforcement |
| --- | --- |
| Project ID and grant revision | Revalidate before each provider request |
| Provider and configured endpoint | Reject a recipient change |
| Relative source paths and content hashes | Restrict reads to the approved source revision |
| Exclusion and size limits | Filter credentials and refuse oversized packets |
| Generated changes | Retain their provenance within the approved repair scope |

A provider change or expanded source inventory requires a renewed approval.
Local filesystem access and isolated execution continue under their own grants.
The contract is approved for implementation. Provider calls remain subject to
the recorded project-specific approval and its exact source inventory.

Use a native local chooser initiated by an authenticated same-origin request.
The server resolves the returned path and creates a short-lived, single-use
selection ticket. Confirmation consumes the ticket. Model payloads reference
existing project IDs. Attachment and detachment update registry metadata.

## File operations

Use directory-descriptor-relative operations with component-by-component
`O_NOFOLLOW` checks. Reject symlinks initially, including links within the root.
Apply exclusions to listings, reads, writes, snapshots and provider packets:
hidden components, credentials, generated environments and dependency trees.
Runtime-owned manifests receive a separate internal interface. Enforce bounded
regular-file reads; reject special files and hard-linked writable sources.
Overlapping roots share an overlap lock and preserve independent grant checks.
Journal-owned recovery artifacts use a separate read/release boundary and remain
excluded from source snapshots and provider inventories. Manual release preserves
the current project files, records interrupted work and erases only the confirmed
recovery objects and journal preimages. Unsupported native exclusivity produces
a diagnostic and retains the affected artifact.

## Execution

Run attached-project commands through a common process launcher. Mount only an
approved snapshot plus required runtime libraries, use private temporary storage,
clear inherited credentials and isolate network unless granted. Keep generated
artifacts outside source folders. Apply verified patch sets through the broker
with input hashes and the existing transaction journal.

Real Python and Node checks exercise the `bwrap` boundary, project-only packages,
private environment/network and bounded output. Fail execution with an actionable
diagnostic where process isolation is unavailable. Revocation cancels owned
process groups and blocks subsequent operations; completed external network
effects remain recorded in the action history.

## Acceptance matrix

| Area | Required observations |
| --- | --- |
| Identity | Restart, per-conversation selection, moved and replaced roots |
| Authority | Forged chooser ticket, stale revision, read-only write, revocation |
| Files | Traversal, encoded paths, symlink swaps, hard links, secret exclusions |
| Concurrency | Overlapping grants, user edits, crash recovery, concurrent runs |
| Processes | Outside-root read/write denial, secret environment, network policy |
| UI | Attach, rights confirmation, navigation, unavailable root, detach |
| Delivery | Disposable Python repair and web preview through production paths |

The [acceptance ledger](LOCAL_PROJECTS_ACCEPTANCE.md) maps these boundaries to
executed checks, production UI journeys and platform limits.
