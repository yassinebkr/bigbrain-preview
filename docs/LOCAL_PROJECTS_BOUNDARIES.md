# Local project boundaries

Phase 1 working specification, 29 October 2026.

## Access inventory

| Boundary | Current implementation | Required integration |
| --- | --- | --- |
| UI filesystem and selection | `web/fs_api.py`, `web/server.py` | Project ID and grant revision on each request |
| Python execution and maintenance | `brains/python_brain.py`, `maintenance.py` | Scoped file broker and isolated runner |
| Web generation and preview | `brains/web_app_brain.py`, `brains/web_stack.py` | Same broker, project-specific scratch and preview leases |
| Verification subprocesses | `verification/executors.py`, `web_gate.py`, `v4_deterministic.py` | Same execution policy as manual runs |
| Recovery | `project_transaction.py` | Preserve hashes and crash journal; bind grant revision |
| Provider transport | `llm/codex_provider.py` and prompt assembly | Explicit source-transmission grant before reads enter prompts |
| Conversation context | Sessions and frontend selection | Persist project identity per conversation |

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

## Execution

Run attached-project commands through a common process launcher. Mount only an
approved snapshot plus required runtime libraries, use private temporary storage,
clear inherited credentials and isolate network unless granted. Keep generated
artifacts outside source folders. Apply verified patch sets through the broker
with input hashes and the existing transaction journal.

The local `bwrap` user-namespace smoke check succeeded. Integration still requires
runtime mount inventories and executable tests. Fail execution with an actionable
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

Each row needs executable evidence in the final acceptance report. The inventory
above identifies integration modules; Phase 2 implementation must trace individual
callers before enabling attached roots in existing workflows.
