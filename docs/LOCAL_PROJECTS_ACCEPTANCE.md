# Attached local projects: acceptance ledger

29 October 2026. Branch: `feat/local-projects`. Status: final acceptance in progress.

## Contract evidence

| Contract | Exercised implementation and assertions | Remaining gate |
| --- | --- | --- |
| Identity and grants | `test_local_projects.py`: persistence, stale revisions, moved/replaced roots and per-conversation selections | Desktop reconciliation journey |
| Chooser authority | `test_local_projects_api.py`: single-use tickets, forged path refusal, same-origin enforcement and detach preservation | Actual Zenity selection on the desktop |
| File containment | `test_local_projects.py`, `test_project_file_io.py`: traversal/exclusions, symlink/hard-link refusal, ancestor substitution and publication races | External-editor atomicity limitation below |
| Source consent and preservation | Provider/planning/maintenance suites: recipient and source revisions, immutable approvals, targeted publication and recovery conflicts | Bounded model-led Python/React probes |
| Process rights and revocation | Real Python/Node tests: private environment/network, read-only dependencies, revocation, timeout and output limits | Browser network/API bypass audit |
| Scratch, preview and continuity | Real Chromium tests plus workspace journey: separate builds, pointer interaction, enlargement, preview closure and result-to-folder identity | Final navigation/refresh and consent-card journeys |

## Verification checkpoints

| State | Result |
| --- | --- |
| Backend at `7a2da2b` | 2,012 passed, 8 skipped |
| Frontend after attached-result navigation | 141 passed |
| Publication and repair evidence integration | 33 targeted cases passed |
| Runtime environment, network and shutdown checks | 6 targeted cases passed |
| Post-audit local-project and orchestrator matrix | 92 passed |

The output-limit regression reproduced a pipe-cleanup deadlock. The runner now
terminates its process group, cancels readers, drains remaining pipe data and
bounds cleanup. Browser verification uses the same drain-before-return principle.

## Explicit limits

- Source proposals currently permit 64 files and 128 KB; individual reads are bounded.
- Host editors operate outside broker locks. Hash checks detect observed changes;
  the final comparison/replacement interval lacks a filesystem compare-and-swap.
- Browser HTTP routing and restricted APIs enforce preview-origin requests.
  Independent browser networking paths still require adversarial coverage.
- Preview frames refresh once per second. Input is pointer/keyboard/text based;
  native file dialogs and downloads are excluded from this preview transport.
- Missing project environments stop verification with a diagnostic. Dependency
  installation requires its own approved preparation workflow.

## Closure

Finish the remaining gates, rerun backend/frontend checks on the final revision,
and record the bounded live-probe evidence. Merge requires user authorization.
