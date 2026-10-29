# Recoverable cross-platform publication

29 October 2026. Proposed design; implementation approval remains pending.
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

## Preservation and conflict policy proposed for approval

1. Keep displaced objects and their journal references after publication. Existing
   editor handles may continue writing to those objects; preservation must retain
   the live object rather than only an earlier byte snapshot.
2. Surface a changed displaced version as a conflict and retain candidate and user
   data. Restoration uses the same protected publication operations.
3. Reserve same-volume preservation storage with explicit project ownership,
   exclusions and access checks. Storage placement and recovery UI require review
   before implementation because attached folders currently keep runtime artifacts
   outside their source trees.
4. Require explicit resolution before deleting preserved objects. Storage limits
   stop new publications and produce a useful diagnostic.
5. Treat missing primitives, unsupported filesystems and ambiguous native results
   as blocked/recovery-required outcomes.

## Qualification milestones

1. Approve the shared behavior, preservation location and retention policy.
2. Implement native adapters and common journal transitions with per-file crash
   injection and atomic destination-collision tests.
3. Test an edit inside the former comparison/rename window, writes through an
   already-open descriptor/handle, interruption, sharing violations, link/path
   substitution and edits during multi-file recovery.
4. Run native Linux/Windows integration jobs and existing regression suites.
   The broader Windows runtime migration remains in [PORTABILITY.md](PORTABILITY.md).

The existing publication race remains open until the new path passes its gates.
