# Cross-platform publication and recovery

30 October 2026. Native publication and release are qualified on Linux and
Windows. Application-level recovery and UI journeys are qualified on Linux.

## Responsibilities

| Layer | Owns |
| --- | --- |
| Shared transaction engine | Permissions, source versions, durable journal, batch recovery and delivery evidence |
| Platform adapter | File identity, native handles, preservation, replacement and durability |
| Workspace | Version inspection, conflict choices and separate cleanup confirmation |

## Publication lifecycle

`Prepare → Publish → Verify → Commit`

A conflict or interruption enters recovery: inspect the actual files, retain
observed versions, obtain version-bound choices and publish through the same engine.

| Step | Required behavior |
| --- | --- |
| Prepare | Pin project/grant identity and input hashes; persist intent and candidate |
| Create | Refuse an occupied destination, including concurrent creation |
| Replace or remove | Retain the actual displaced live object and record its identity |
| Verify | Compare displaced content with the expected version; recheck project and candidate |
| Recover | Reconcile native state after interruption and preserve concurrent editor changes |

Multi-file visibility advances per file. The journal coordinates commit and
rollback across the batch.

## Preservation and conflicts

| Boundary | Policy |
| --- | --- |
| Editor changes | Retain live displaced objects, including later writes through existing handles |
| Conflicts | Block delivery and further mutation/execution; expose candidate and retained versions |
| Resolution | Bind every choice to journal, source and retained-object versions; changed observations require fresh inspection |
| Storage | Owned project-local `.bigbrain-recovery`, on the affected volume; 256 MiB / 4,096 retained files |
| Exclusions | Recovery data stays outside source scans, ordinary file access and provider inventories |
| Unsupported state | Missing primitives, incompatible mounts, quota exhaustion or ambiguous results block publication |

Restoration retains the displaced candidate. Later editor writes reopen the conflict.

## Native mechanisms

| Operation | Linux | Windows |
| --- | --- | --- |
| Preserve replacement | `renameat2(RENAME_EXCHANGE)` | `ReplaceFileW` with same-volume backup |
| Create exclusively | `RENAME_NOREPLACE` | `MoveFileExW` without replacement |
| Release retained object | Isolated helper holding a kernel write lease | Exclusive file handle with deletion disposition |

Adapters inspect resulting paths and identities after failures. Filesystem support
and durability require qualification; cross-volume copy/delete is outside this scope.
Windows replacement has documented partial-failure states and an unsupported
write-through flag.

API references: [Linux rename](https://man7.org/linux/man-pages/man2/rename.2.html),
[Linux leases](https://man7.org/linux/man-pages/man2/F_SETLEASE.2const.html),
[Windows replacement](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-replacefilew),
[Windows move](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-movefileexw),
[Windows disposition](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-setfileinformationbyhandle).

## Manual recovery cleanup

1. Inspect a resolved, terminal transaction. Display exact artifacts, hashes and sizes.
2. Require the deletion grant and separate confirmation of irreversible cleanup.
3. Persist original/private-quarantine names, then acquire native exclusivity.
   Changed bytes, identities, open editor handles or hard links refuse release.
4. Remove confirmed recovery objects and journal preimages; retain hashes and
   receipts. Preserve current project sources and remove empty owned directories.

Editors must close old handles before cleanup. Writes through a surviving handle
after deletion fall outside the recovery guarantee.

A request starts file operations for at most 15 seconds; each Linux helper has an
8-second ceiling. The registry grant boundary stays held through the bounded batch.
Rights changes govern subsequent requests.

Interrupted cleanup remains inspectable and blocks mutation/execution. Resumption
requires a fresh inventory and confirmation; remaining artifacts stay readable.

## Verification

| Boundary | Recorded result |
| --- | --- |
| Complete backend collection | 2,074 passed, 8 optional extractor-experiment skips; 2,082 collected |
| Frontend | 141 passed; production build passed |
| Native publication/release at `1dbbf86` | 14 Ubuntu and 14 Windows cases passed; zero skips |
| Application conflict resolution | 8 regression cases and production UI restoration |
| Application cleanup | 10 regression cases and production UI cleanup of a synthetic 26-byte backup and journal preimages; current source preserved |
| Attached React builds | 4 real Node/React cases preserve dependencies and existing source-side build artifacts |

[Native CI results](https://github.com/yassinebkr/bigbrain-preview/actions/runs/40973915789)
and the [acceptance ledger](LOCAL_PROJECTS_ACCEPTANCE.md) provide qualification
scope, reports and UI evidence.

## Remaining platform work

Broader Windows filesystem, locking, runner and chooser adaptation follows
[the portability backlog](PORTABILITY.md). Attached React builds use copied
sources and bounded captured artifacts. Legacy sandbox build-tree recovery has
a separate audit boundary.
