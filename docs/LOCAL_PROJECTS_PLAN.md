# Attached local projects

30 October 2026. Branch: `feat/local-projects`.
Implementation and acceptance are verified within the platform/capability matrix.

## Access and preservation contracts

1. Persist project identity, canonical root and explicit read-only/read-write
   grant. Conversations reference the project independently of its lifecycle.
2. A trusted local chooser authorizes roots. Model-proposed paths cannot grant
   access. Relevant brains enforce the same grant at every tool boundary.
3. Resolve symlinks and refuse root escapes. Define exclusions for credentials,
   hidden files and generated folders. Attachment grants no blanket indexing,
   embedding or transmission to providers.
4. Preserve user changes, version patch inputs and detect concurrent edits.
   Inspect actual manifests and entry points with provenance.
5. Separate access from execution, deletion, package-installation and network
   permissions. Define revocation during active work and after restart.
6. Separate scratch/preview artifacts from sources. Show path and rights. Test
   unavailable drives, renames, overlapping roots, concurrent edits, symlink
   escapes, revocation and restoration. Detachment preserves user files.

## Delivered phases and milestones

| Phase | Milestone and evidence |
| --- | --- |
| 1 — Architecture boundary | Access inventory, immutable source-consent contract, native publication and retention policy; [boundaries](LOCAL_PROJECTS_BOUNDARIES.md) |
| 2 — Registry and filesystem | Persistent IDs/revisions, trusted chooser tickets, scoped descriptors, exclusions, overlapping roots, read-only/revoked states and native moved-folder reconciliation |
| 3 — Modification and execution | Shared repair engine, candidate/published checks, retained source publication, isolated Python/Node and real browser verification, project dependencies and bounded cancellation |
| 4 — Attachment and continuity | Production UI covers consent/rejection, rights, navigation/reload, unavailable folders, detach, streamed output, interactive preview, conflict resolution and confirmed recovery release |
| 5 — Cross-path acceptance | 2,074 backend cases passed / 8 optional skips; 141 frontend cases and build passed; native publication/release: 14 Ubuntu / 14 Windows cases passed |

The [acceptance ledger](LOCAL_PROJECTS_ACCEPTANCE.md) maps all six contracts to
executed assertions, native UI journeys, bounded model-led Python/React probes,
reports and remaining capability limits.

## Runtime contracts

- Conversation selection records its active origin separately from the remembered
  local-folder ID. Local-origin prompts exclude stale sandbox navigation hints.
- Every source-bearing model request checks the user-confirmed provider/endpoint,
  project/grant revision and exact source inventory. A changed recipient or
  inventory requires renewed user consent. Current proposal limits: 64 files, 128 KB.
- Maintenance uses the existing repair engine on a scoped working copy.
  Candidate checks precede publication; published changes receive another
  isolated check before commit. Delivery evidence binds specification revision,
  recipient, source versions, checks and publication outcome.
- Python/Node execution uses Bubblewrap, private temporary storage, read-only
  project dependencies, bounded output/time and revocation-aware process cleanup.
  Incompatible environments produce explicit diagnostics.
- Attached React/Vite builds run on copied sources and capture bounded artifacts.
  The host project's existing `dist` and dependencies remain preserved.
- Preview leases expose rendered frames with pointer, keyboard, text and scroll
  input. They close on navigation, visibility changes, revocation or inactivity.
- Source writes and rollback retain the displaced live file. A changed retained
  version blocks further mutation/execution and supports version-bound recovery
  choices through the same publication engine.
- Manual recovery release requires a terminal transaction, the deletion grant,
  exact inventory and separate irreversible confirmation. Interrupted release
  remains inspectable and resumable. Changed or open artifacts refuse deletion.
  Storage limits: 256 MiB and 4,096 retained files; reaching them stops publication.

Publication details: [recoverable publication](PUBLICATION_PORTABILITY_DESIGN.md).

## Platform and capability limits

Linux application paths and production UI are qualified. Native publication and
release primitives are qualified on Linux and Windows. The broader Windows
filesystem/lock/runner/chooser migration follows the deferred backlog in
[PORTABILITY.md](PORTABILITY.md). The shared policy applies to future blocks.

Dependency installation and network-enabled execution require separate permissioned
workflows. Preview frames refresh once per second; native file dialogs and
downloads remain outside this transport. Release requires supported native
exclusivity; unsupported filesystems retain the artifacts and return a diagnostic.
Legacy sandbox generated-build-tree recovery has a separate audit boundary.

## Following milestone — CAD brain and piece preview

Close the CAD artifact/preview contract, then implement a dedicated SolidCraft
adapter using this project/access foundation. Keep headless computation, native
history, geometry checks, revision-bound fast previews and optional GUI handoff.
Show the piece as a compact expandable object in the main work surface; expose
stale and failed updates.

Start with the dimensioned plate, enclosure, parameter-edit and rollback cases
from [SolidCraft qualification](SOLIDCRAFT_QUALIFICATION_20261029.md).
Autonomous modeling and interactive preview require their own acceptance.
Photos/diagrams follow later with explicit scale and uncertainty; shared-focus
architecture and printer control remain deferred.
