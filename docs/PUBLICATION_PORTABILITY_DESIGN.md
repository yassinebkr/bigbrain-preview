# Recoverable cross-platform publication

29 October 2026. Preservation location and retention approved; implementation underway.
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

The existing publication race remains open until the new path passes its gates.

## Implementation checkpoint

`native_publication.py` provides Linux and Windows primitives under a common
create/replace-preserving/retire interface. Source writes and rollback now record
native intent before publication, reconcile interrupted operations and retain
displaced live objects. Direct attached-project writes and single-file helpers
use the same journal. Recovery storage checks ownership and enforces a 256 MiB
limit. The focused Linux matrix passes 73 tests, including delivery, registry,
recovery API and native publication. The frontend passes 141 tests and its build.
The workspace can inspect a bounded retained version and its SHA-256
through a project/operation-bound read endpoint. Current full regression,
conflict resolution, retention management and generated build-tree publication
remain open.

Commit `1131536` passes nine native primitive cases on Ubuntu and nine on Windows,
with zero skips. Cases include late editor writes and directory identity anchors.
[Native CI run](https://github.com/yassinebkr/bigbrain-preview/actions/runs/40970102017).
The application-level journal matrix runs on Linux; broader Windows runtime
adaptation remains deferred in [PORTABILITY.md](PORTABILITY.md).

Production UI acceptance on an isolated synthetic project displays the retained
late editor write and its SHA-256 while preserving the published candidate.
Screenshot: `/tmp/bigbrain-retained-version-ui.png`. Four transmission tests pass,
including recovery-directory exclusion from source consent and normal file access.

The full `1131536` run reached 95% without reported failures, then terminated
with exit 143 before writing its JUnit report. Its final three test files pass
separately: 90 cases, `/tmp/bigbrain-publication-tail.xml`. Full-run completion
remains an open gate.
