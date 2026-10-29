# Attached local projects: acceptance ledger

29 October 2026. Branch: `feat/local-projects`. Status: final acceptance in progress.

## Contract evidence

| Contract | Exercised implementation and assertions | Remaining gate |
| --- | --- | --- |
| Identity and grants | `test_local_projects.py`: persistence, stale revisions, moved/replaced roots and per-conversation selections | Desktop reconciliation journey |
| Chooser authority | `test_local_projects_api.py`: single-use tickets, forged path refusal, same-origin enforcement and detach preservation | Actual Zenity selection on the desktop |
| File containment | `test_local_projects.py`, `test_project_file_io.py`: traversal/exclusions, symlink/hard-link refusal, ancestor substitution and publication races | External-editor atomicity limitation below |
| Source consent and preservation | Provider/planning/maintenance suites, live Python/React repairs and production proposal/rejection UI: immutable recipient, source revisions and targeted publication | Complete within the tested matrix |
| Process rights and revocation | Real Python/Node tests and Worker network probes: private environment/network, read-only dependencies, revocation, timeout and output limits | Complete within the tested matrix |
| Scratch, preview and continuity | Production UI: interaction, enlargement, closure, navigation, recovery, revoke/restore, read-only execution denial and detach preservation | Native chooser and moved-folder reconciliation |

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

## Explicit limits

- Source proposals currently permit 64 files and 128 KB; individual reads are bounded.
- Host editors operate outside broker locks. Hash checks detect observed changes;
  the final comparison/replacement interval lacks a filesystem compare-and-swap.
- Browser HTTP routing, response CSP and restricted APIs limit preview requests.
  This browser-layer policy remains separate from OS network namespaces used by
  Python and Node execution.
- Preview frames refresh once per second. Input is pointer/keyboard/text based;
  native file dialogs and downloads are excluded from this preview transport.
- Missing project environments stop verification with a diagnostic. Dependency
  installation requires its own approved preparation workflow.

## Closure

Finish the remaining gates, rerun backend/frontend checks on the final revision,
and record the bounded live-probe evidence. Merge requires user authorization.
