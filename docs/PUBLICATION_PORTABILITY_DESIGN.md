# Recoverable cross-platform publication

30 October 2026. Source publication, conflict resolution and manual release
are qualified within the recorded platform and capability matrix.
Applies to the shared transaction engine and attached-project publication.

## Shared contract

| Operation | Required outcome |
| --- | --- |
| Prepare | Pin project/grant identity and expected source version; persist intent and candidate before publication |
| Create | Refuse an existing destination, including a concurrent creation |
| Replace | Retain the file actually displaced by publication and record its identity/version |
| Remove | Retain the removed object as recoverable data and validate its observed version |
| Verify | Compare displaced content with the expected version and recheck candidate/project identity |
| Conflict | Stop delivery, retain every observed version and expose recovery references |
| Recover | Inspect actual native state after interruption; preserve concurrent edits during restoration |

The common engine owns permission checks, journal transitions, batch coordination
and evidence. Platform adapters own native file identity, handles, preservation,
publication and durability operations. Multi-file visibility advances per file;
the journal coordinates commit and recovery across the batch.

## Native candidates and documented differences

- Linux `renameat2(RENAME_EXCHANGE)` exchanges two existing paths atomically.
  `RENAME_NOREPLACE` refuses an occupied destination and requires filesystem
  support. Renaming leaves existing open descriptors attached to their objects.
  [Linux manual](https://man7.org/linux/man-pages/man2/rename.2.html).
- Windows `ReplaceFileW` accepts a backup path on the same volume. Its documented
  failure states include renamed originals and partially transferred metadata;
  its write-through flag is unsupported. The adapter must inspect resulting
  paths/identities and qualify durability separately.
  [Microsoft reference](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-replacefilew).
- Windows `MoveFileExW` exposes replacement and cross-volume-copy options. The
  create operation requires a separately qualified destination-exists refusal
  path. Cross-volume copy/delete remains outside the initial publication scope.
  [Microsoft reference](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-movefileexw).

API documentation establishes candidate semantics. Acceptance requires actual
native tests on each supported filesystem and operating system.

## Approved preservation and conflict policy

1. Keep displaced objects and their journal references after publication. Existing
   editor handles may continue writing to those objects; preservation must retain
   the live object rather than only an earlier byte snapshot.
2. Surface a changed displaced version as a conflict and retain candidate and user
   data. Restoration uses the same protected publication operations.
3. Reserve `.bigbrain-recovery` inside each linked project with explicit project
   ownership, exclusions and access checks. Keep backups on the affected file's
   volume; a nested mount with incompatible storage blocks the operation.
   Recovery contents stay outside source scans and provider transmission.
4. Require explicit resolution before deleting preserved objects. Storage limits
   stop new publications and produce a useful diagnostic.
5. Treat missing primitives, unsupported filesystems and ambiguous native results
   as blocked/recovery-required outcomes.

## Qualification milestones

1. Approved: shared behavior, project-local hidden storage and explicit retention.
2. Implement native adapters and common journal transitions with per-file crash
   injection and atomic destination-collision tests.
3. Test an edit inside the former comparison/rename window, writes through an
   already-open descriptor/handle, interruption, sharing violations, link/path
   substitution and edits during multi-file recovery.
4. Run native Linux/Windows integration jobs and existing regression suites.
   The broader Windows runtime migration remains in [PORTABILITY.md](PORTABILITY.md).

The qualification below defines the exercised publication and release boundaries.

## Implementation checkpoint

`native_publication.py` provides Linux and Windows primitives under a common
create/replace-preserving/retire interface. Source writes and rollback now record
native intent before publication, reconcile interrupted operations and retain
displaced live objects. Direct attached-project writes and single-file helpers
use the same journal. Recovery storage checks ownership and enforces a 256 MiB
limit. The focused Linux matrix passes 73 tests, including delivery, registry,
recovery API and native publication. The frontend passes 141 tests and its build.
The workspace can inspect a bounded retained version and its SHA-256
through a project/operation-bound read endpoint. Explicit conflict resolution
binds every file choice to the journal, source versions and retained objects.
Restoration uses the same publication/rollback engine and retains the displaced
candidate. Changed observations require another inspection. Later editor writes
reopen the conflict. Eight resolution regressions pass.

The production UI restores a chosen retained editor version and clears the
resolved conflict. Evidence: `/tmp/bigbrain-resolved-version-ui.png`.
Manual retention release passes its application and production UI gates.

### Approved manual retention release

Approved on 30 October 2026:

- Keep retained objects until a separate irreversible-release confirmation.
- Require the deletion grant, a resolved transaction and a version-bound inventory.
- Show affected versions and storage size before confirmation; refuse changed
  observations and preserve the objects for renewed inspection.
- Warn that editors must close their old file handles before release. Writes
  through a surviving handle after deletion fall outside the recovery guarantee.
- Qualify release, interruption and concurrent-change behavior with disposable
  fixtures before enabling the action. Personal project cleanup remains a user action.

Native release uses a short-lived Linux helper holding a write lease, or an
exclusive Windows file handle with deletion disposition. Changed bytes, changed
file identity, open editor handles and hard links refuse release. Linux signals
remain confined to the helper. Commit `1dbbf86` passes fourteen native cases on
Ubuntu and fourteen on Windows, with zero skips.
[Native release CI](https://github.com/yassinebkr/bigbrain-preview/actions/runs/40973915789).
[Linux lease contract](https://man7.org/linux/man-pages/man2/F_SETLEASE.2const.html),
[Windows file disposition](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-setfileinformationbyhandle).

The UI lists terminal journals, exact artifacts, hashes and byte sizes. Release
records both original and private quarantine names before movement. A request
spends at most fifteen seconds starting file operations; each Linux helper has
an eight-second ceiling. Partial work remains pending and blocks new mutation
and execution until a fresh inventory receives another confirmation. Remaining
artifacts stay readable. Finalization scrubs journal recovery preimages while
retaining their hashes and receipts; empty owned directories are removed.
Each confirmed batch holds the registry grant boundary through its native work.
Rights changes apply after that bounded batch and govern subsequent requests.

Ten application regressions cover permissions, HTTP confirmation, changed data,
open handles, interruption before/after deletion, foreign roots and resumed work.
The separately authorized production UI journey released one synthetic 26-byte
artifact and its journal preimages. The current `main.py` stayed unchanged.
Evidence: `/tmp/bigbrain-retention-confirmation-ui.png` and
`/tmp/bigbrain-retention-purged-ui.png`. The final split campaign passes 2,074 cases
with eight optional skips; frontend 141 cases and the production build pass.

Attached React builds run on copied sources through `ProjectRunner`, capture
`dist` as bounded artifacts and serve those captured bytes. Four real Node/React
tests preserve dependencies and an existing source-side `dist/user-artifact.txt`.
Legacy sandbox build-tree recovery remains a separate shared-engine audit area.

Commit `1131536` passes nine native primitive cases on Ubuntu and nine on Windows,
with zero skips. Cases include late editor writes and directory identity anchors.
[Native CI run](https://github.com/yassinebkr/bigbrain-preview/actions/runs/40970102017).
The application-level journal matrix runs on Linux; broader Windows runtime
adaptation remains deferred in [PORTABILITY.md](PORTABILITY.md).

Production UI acceptance on an isolated synthetic project displays the retained
late editor write and its SHA-256 while preserving the published candidate.
Screenshot: `/tmp/bigbrain-retained-version-ui.png`. Four transmission tests pass,
including recovery-directory exclusion from source consent and normal file access.

The monolithic `1131536` run terminated with exit 143 at 95%. The replacement
exhaustive final split campaign passes 2,074 cases with eight skips; the collection
contains 2,082 cases. Reports and accounting are in the
[acceptance ledger](LOCAL_PROJECTS_ACCEPTANCE.md).
