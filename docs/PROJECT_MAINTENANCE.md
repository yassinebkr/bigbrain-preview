# Project maintenance: implementation and validation ledger

2026-10-21. Branch `feat/project-maintenance`, based on merged shared-memory
baseline `414df4a`. No authorization to merge this new phase.

## Why a separate workflow

Creation uses an architect/file DAG. Repair needs an investigation loop: inspect,
reproduce, hypothesize, patch, measure. Freezing an implementation file list
before investigation made repair impossible when only tests were approved.
Global snapshots also exceeded budgets without giving the model a way to select
the relevant sources. Raising those budgets is not the solution.

## Ordered plan

1. Keep creation, bus authentication, project identity, approval, Stop, project
   environments, revision checks, rollback and durable evidence.
2. Add a typed, bounded maintenance loop owned by the appropriate specialist.
   Progressive list/search/read, real diagnostics, exact patches, verification.
   No full-project source injection. Source and tool output are untrusted data.
3. Approve objective, project boundary, acceptance and action/time budgets.
   Do not preselect all implementation files. Changes to existing tests or
   expected behavior require explicit arbitration. Runtime owns manifests.
4. Journal discovered source writes before modifying them; reject stale reads,
   concurrent changes, unsafe paths and writes after Stop. Preserve rollback.
5. Integrate PythonBrain and WebAppBrain separately with orchestrator approval
   and existing Atelier events. No keyword-based routing. Independent final
   verification cannot be replaced by the worker's completion claim.
6. Exercise frozen cases: local defect, cross-module defect, contradictory test,
   missing environment, large selective context, Stop, concurrent edits and
   rollback. Compare identical inputs against the previous workflow.
7. Record success, regressions, changed files, model calls/usage if available,
   duration, interventions and limitations. Fake providers validate protocol,
   not model competence. Use real configured providers for competence evidence.
8. Validate a disposable copy of the real G-code project through BigBrain; do
   not hand-fix the original or ask the user to keep blindly retrying.
9. Run focused/full Python gates and applicable UI checks, inspect diff, update
   roadmap and this ledger. Merge only after user validation.

## Boundaries

Project tests/programs execute code; this is not an OS security sandbox. Source
transactions do not roll back arbitrary program side effects or installations.
An inconclusive check is not a demonstrated code defect. LLM review is not a
proof of domain truth. Keep missing live evaluations explicitly unverified.

## Evidence ledger

- Baseline: 1158 Python tests / 9 warnings, 101 UI tests and build passed before
  merge. Shared-memory lot merged/pushed; user runtime files excluded.
- Implemented: a project-scoped maintenance task, objective approval without a
  guessed per-file DAG, one specialist tool loop, paged sources/diagnostics,
  exact revision-checked patches and dynamic transaction reservation.
- Existing tests/configuration stay approval-gated. New regression test files
  consistent with the objective are allowed; no blanket permission to rewrite
  existing tests. Runtime compares their hashes before/after verification.
- Python diagnostics use project Python. Missing tooling is inconclusive; an
  explicit prepare action provisions the declared environment, never host
  fallback. Web diagnostics use the actual static/build/browser pipeline.
- Final review reads source pages independently and links every criterion to
  actual executed test IDs or scoped runtime preservation proofs. A concrete
  missing assertion can request additional evidence; conflicting requirements
  require arbitration. Worker completion claims cannot pass the gate.
- Action observations are content-addressed artifacts. Failed/cancelled work
  rolls back via the existing orchestrator transaction. New/late/stale writes
  are rejected. Source inventory is bounded; hashes are not injected as a full
  source snapshot. Test stdout collection is capped at 2 MB before truncation.
- Local gates: 1182 full Python tests passed (152.21 s, 9 existing warnings),
  102 UI tests and build passed. Additional targeted tests cover the
  real bus/approval/commit lifecycle, real Chromium repair, preservation, source
  pagination, stale reads, output flooding, Stop and rollback. A final additional
  test covers safe HTTP-status diagnostics without leaking provider secrets.
- Live G-code copy: reproduced baseline conflicts and requested arbitration
  without changing any file (50.28 s, 9 calls, 36845 provider-reported tokens).
  Temperature-origin expectations conflict with the requested provenance rule;
  the two suites also disagree about M82/G91. No manual repair and no original
  project modification. Harness supplied fixture metadata/entry point, so this
  does not prove automatic legacy-manifest recovery or user UI approval.
- Exploratory live comparisons are retained as failed/inconclusive evidence,
  not advertised as successes. One early comparison was invalidated by a
  recording-wrapper positional-argument bug; interrupted campaigns do not count
  as completed comparisons. A reliable final competence comparison is not yet
  complete; do not infer a speed, cost or success-rate advantage.

### Live outcomes and current blocker

Native-tool cross-module validation succeeded: 147.61 s, 32 calls, 53821 tokens.
Only `arithmetic.py`, a new regression test and runtime `.project.json` changed.
The first independent review requested extra executed evidence; the specialist
added the test and the next review passed. This is one sample, not a reliability
claim. Evidence: `/tmp/bigbrain-maintenance-campaign-l8ce3c2k`.

The user-approved G-code test corrections were exercised on the disposable copy:
all deterministic stages passed, but the earlier text-protocol independent review
timed out (286.41 s, 186551 tokens). Delivery stayed rejected and changes rolled
back. Evidence: `/tmp/bigbrain-maintenance-campaign-s5whoa4f`.

The native-protocol G-code run stopped on an HTTP provider error (129.42 s,
140334 tokens). Original hashes matched; transaction rolled back with zero
remaining changed files. Evidence: `/tmp/bigbrain-maintenance-campaign-_u3792y4`.
The subsequently authorized five-case synthetic campaign was also interrupted by
HTTP errors, including its local-case final review. These outcomes are NOT code
failures or successful deliveries. Evidence:
`/tmp/bigbrain-maintenance-campaign-_wy4mmcu`.

A read-only OpenRouter `/credits` check confirmed exhausted credit. No further
paid calls are running or scheduled. Earlier exception capture retained only the
exception class, so do not invent exact HTTP status codes for those requests.
Subsequent evidence capture now retains status only, never request headers or raw
provider bodies. Final native G-code acceptance and the completed native frozen
campaign remain unverified until provider access is restored and the user agrees
to resume spending. No silent model/provider substitution, no merge, no claim
that this phase or its active goal is complete.

## Provider protocol

The worker and progressive reviewer use a native single named function call on
the OpenAI-compatible provider, with no silent text fallback. Exactly one matching
call and JSON-object arguments are required. A strict JSON-schema response is
also supported by the provider, but exploratory trials exposed malformed/truncated
text protocol responses; those did not count as delivery. OpenRouter's documented
`require_parameters` preference prevents routing to endpoints that discard the
required protocol. The Sol 6.1 endpoint metadata was inspected:
temperature is unsupported there, so its registry capability now omits it. Stream
options are sent only for streaming. A live minimal schema request succeeded.
Other models/endpoints must support the requested tool protocol or review stays
inconclusive; no model switch or parsing of a partial final verdict is performed.

References: [structured outputs](https://openrouter.ai/docs/guides/features/structured-outputs),
[tool calling](https://openrouter.ai/docs/guides/features/tool-calling).

## Reproduction

` .venv/bin/python tools/run_maintenance_campaign.py --live --case all --compare `
opts into paid model calls on disposable synthetic projects. Without `--live`
the command refuses to call a provider. `--case gcode` sends a disposable source
copy to the configured model and requires the user's explicit data-sharing
authorization (obtained in this thread). Hidden/environment files are excluded.
Private raw replies, source hashes, usage and per-case results remain in the
printed temporary evidence folder. Fixture approval is synthetic, not a claim of
real user approval. The optional `--approve-gcode-conflicts` flag is allowed only
after explicit approval of the two documented test semantic corrections; it does
not authorize changing the original. That approval was obtained in this thread.
Missing prices stay unknown; token counts are provider data,
not estimated from character counts.
