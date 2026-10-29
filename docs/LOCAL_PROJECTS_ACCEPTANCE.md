# Attached local projects: acceptance ledger

29 October 2026. Branch: `feat/local-projects`. Status: final acceptance in progress.

## Contract evidence

| Contract | Exercised implementation and assertions | Remaining gate |
| --- | --- | --- |
| Identity and grants | Offline cases and native reconciliation: persistence, stale revisions, moved/replaced roots, per-conversation selections, preserved UUID/inode/grants | Complete within the tested matrix |
| Chooser authority | Native Zenity selection, production confirmation and HTTP cases: single-use tickets, forged path refusal, same-origin enforcement and detach preservation | Complete within the tested matrix |
| File containment | `test_local_projects.py`, `test_project_file_io.py`: traversal/exclusions, symlink/hard-link refusal, ancestor substitution and publication races | External-editor atomicity limitation below |
| Source consent and preservation | Provider/planning/maintenance suites, live Python/React repairs and production proposal/rejection UI: immutable recipient, source revisions and targeted publication | Complete within the tested matrix |
| Process rights and revocation | Real Python/Node tests and Worker network probes: private environment/network, read-only dependencies, revocation, timeout and output limits | Complete within the tested matrix |
| Scratch, preview and continuity | Production UI: interaction, enlargement, closure, navigation, recovery, revoke/restore, read-only execution denial, detach and native reconciliation | Complete within the tested matrix |

## Verification checkpoints

| State | Result |
| --- | --- |
| Backend at `7a2da2b` | 2,012 passed, 8 skipped |
| Full backend at `93e4162` | 2,029 passed, 8 skipped, 227.75 seconds |
| Full backend campaign launched at `57a42fe` | 2,021 passed, 8 skipped, 1 dispatch timeout; exact-text changes received separate targeted checks |
| Frontend after attached-result navigation | 141 passed |
| Publication and repair evidence integration | 33 targeted cases passed |
| Runtime environment, network and shutdown checks | 6 targeted cases passed |
| Post-audit local-project and orchestrator matrix | 92 passed |
| Origin/context navigation gate | 34 passed; production UI exercised origin switching, reload and an empty new-conversation choice |
| Current source publication/resolution campaign | 2,059 passed, 8 skipped across exhaustive split groups and updated Node cases; 2,067 collected |
| Current frontend | 141 passed; production build passed |
| Native primitives at `1131536` | 9 Ubuntu and 9 Windows cases passed, zero skips |

Current regression reports: `/tmp/bigbrain-regression-am.xml` (868 passed,
8 skipped), `/tmp/bigbrain-regression-nz.xml` (1,190 passed), and
`/tmp/bigbrain-regression-node.xml` (four updated cases, including one additional
existing-build case). The split campaign covers the complete current collection.
The WebSocket acknowledgement test now awaits its actual delivery task with a
two-second bound; message, provenance, persistence and acknowledgement assertions
remain unchanged.

## Bounded model-led probes

GPT-6.1 Sol low through the Codex subscription. Each case had a ten-call,
300-second ceiling. Only synthetic sources and diagnostics were transmitted.
The executable was resolved to `/usr/lib/chatgpt/resources/codex` after the initial
launch environment failed to locate it; those launch failures produced no inference.

| Case | Outcome | Calls | Seconds | Reported input/output tokens |
| --- | --- | ---: | ---: | --- |
| Python addition and CLI | Verified; corrected `arithmetic.py`, added `test_cli.py`, published after checks | 5 | 37.460 | 23,704 / 643 across 3 usage records; 2 calls have unreported usage |
| React counter | Arbitration; preserved sources after inconsistent browser evidence | 2 | 24.077 | 13,872 / 407 across 2 usage records |
| React counter, exact assertion | Verified; corrected only `src/main.jsx`; build, browser assertion, review and publication passed | 3 | 31.634 | 14,489 / 347 across 2 usage records; 1 call has unreported usage |

The React scenario used substring matching: `1` matched the incorrect value `-1`.
The model compared the source, assertion and observed page, identified the
contradiction and stopped. The runtime now supports `text_equals` for exact
counter/state assertions while preserving the existing substring operation.
Regression checks cover `1`, `-1` and `10`; the 21-case browser/adapter suite passes.
The separately authorized exact-assertion probe closes the React delivery gate.
Subscription cost is unknown. Missing usage records remain explicitly uncounted.
Local reports: `/tmp/bigbrain-local-live-yiyftz27/{python,web_app}-report.json`.
Exact-assertion report: `/tmp/bigbrain-local-live-2rix6q02/web_app-report.json`.

The full campaign timed out in
`TestReentrantEvents.test_noisy_brain_high_event_throughput`: two subtasks remained
running after its five-second polling deadline. The same test passed in isolation.
An injected slow-fsync test reproduced event-loop blocking in the bus logger.
Journal writes now run on a serialized I/O thread, retain per-message fsync and
drain active writes before cancellation or close. The 46-case logger/bus/dispatch
suite passes. The complete campaign at `93e4162` also passes.

A real blob Worker opened a WebSocket to another loopback service despite the
page-level constructor restrictions. Preview responses now carry a restrictive
Content Security Policy inherited by blob workers. Adversarial WebSocket and
fetch cases verify execution, blocked outcomes and zero requests at the target.
The 13-case preview/web/Node suite passes, including the React build path.

The output-limit regression reproduced a pipe-cleanup deadlock. The runner now
terminates its process group, cancels readers, drains remaining pipe data and
bounds cleanup. Browser verification uses the same drain-before-return principle.

The server stores each conversation's active origin separately from its remembered
folder ID. The front suppresses sandbox navigation hints while the local origin
is active. Invalid selection metadata produces an unavailable context and a
terminal conversational response.

Production UI acceptance used isolated servers and artificial folders. Recovery
restored the original file; revocation/restore retained the grant identity;
read-only mode disabled execution; detachment preserved the source on disk.
The proposal journey used supplied fixture criteria and the production
orchestrator, immutable specification, journal and WebSocket bridge. The UI showed
the actual Codex recipient and source SHA-256. Rejection persisted as specification
revision 2 and remained terminal after reload. This UI journey made zero model calls.
Local visual evidence: `/tmp/bigbrain-local-recovery-ui.png`,
`/tmp/bigbrain-local-readonly-ui.png`, `/tmp/bigbrain-local-source-consent-ui.png`.

Native reconciliation used the desktop Zenity chooser and production rights
confirmation. The moved artificial root retained UUID
`c6845801-2fda-4605-a777-d49e617e545b`, device/inode `40:179510` and its four
grants; revision advanced from 1 to 2. The source remained `print(42)` and the
selection survived reload. Visual evidence: `/tmp/bigbrain-local-native-relink.png`.
The initial expired ticket was rejected without changing the registry.

## Explicit limits

- Source proposals currently permit 64 files and 128 KB; individual reads are bounded.
- Host editors operate outside broker locks. Source writes and rollback retain
  the displaced live object. Linux regressions preserve edits inside the native
  publication window and later writes through open editor descriptors. Conflicts
  block further mutation/execution and expose retained versions in the workspace.
  Version-bound explicit resolution passes eight regression cases and a real
  workspace journey. Restoring the retained editor version preserves the
  displaced candidate and closes the observed conflict. Retention management
  remains open. Attached React builds preserve an existing source-side dist;
  legacy sandbox build-tree recovery remains a separate audit area.
  Historical failing evidence:
  `/tmp/bigbrain-publication-window-j42yyqd5/result.json`.
- Browser HTTP routing, response CSP and restricted APIs limit preview requests.
  This browser-layer policy remains separate from OS network namespaces used by
  Python and Node execution.
- Preview frames refresh once per second. Input is pointer/keyboard/text based;
  native file dialogs and downloads are excluded from this preview transport.
- Missing project environments stop verification with a diagnostic. Dependency
  installation requires its own approved preparation workflow.

## Closure

Functional, native UI and model-led gates pass. The external-editor publication
hardening now has approved project-local hidden recovery storage and explicit
retention. Commit `6806680` passes eight primitive cases on Linux and eight on
Windows in native CI, with zero skips. Commit `1131536` extends this to nine cases
on each platform. Shared-journal source integration, version-bound resolution,
production UI restoration and the complete split regression campaign pass on
Linux. Retention management remains open. See the
[publication design](PUBLICATION_PORTABILITY_DESIGN.md).
Merge requires user authorization.
