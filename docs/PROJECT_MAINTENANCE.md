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
- Local gates: final 1183 full Python tests passed (150.59 s, 9 existing warnings),
  102 UI tests and build passed. Additional targeted tests cover the
  real bus/approval/commit lifecycle, real Chromium repair, preservation, source
  pagination, stale reads, output flooding, Stop and rollback, including safe
  HTTP-status diagnostics without leaking provider secrets.
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

A read-only OpenRouter `/credits` check confirmed exhausted credit. At that
checkpoint paid calls stopped; the later Mistral continuation was explicitly
authorized. Earlier exception capture retained only the
exception class, so do not invent exact HTTP status codes for those requests.
Subsequent evidence capture now retains status only, never request headers or raw
provider bodies. Successful G-code acceptance remains unproven; completed Mistral
comparison results are recorded below. No silent model/provider substitution, no merge, no
claim that this phase or its active goal is complete.

### Mistral Studio continuation (2026-10-22)

User explicitly authorized Mistral Large 4 through Studio for the upcoming tests;
authenticated `/models` confirmed reasoning, function calling and vision. Studio
credentials remain separate from Vibe, are loaded from the existing durable key
file as well as `.env`, and never enter experiment artifacts.

The connector now filters Mistral chunk-list responses to visible text only,
including streaming. Thinking chunks do not become worker JSON or chat text.
Native single-action requests explicitly disable parallel tool calls. High
reasoning was selectable with `MISTRAL_STUDIO_LARGE_4_REASONING_EFFORT=high`;
the initial default was `none`. Those early high-mode requests reserved 8192 extra output
tokens and up to 180 seconds per call. Progressive independent review allows
360 seconds in this mode; maintenance still stops at 40 actions / 600 seconds.
These are bounded runtime allowances, not claims about model speed or competence.

Initial local trials: one native protocol rejection (no writes), one manually
interrupted after alternating valid and flattened invalid actions (transaction
rolled back), one high-mode contract timeout at the former 20-second limit.
They are failed/incomplete trials, not deliveries. The action loop now explains
the exact expected nested shape and stops after three consecutive malformed
actions instead of spending its whole action budget on them.

The high-mode local trial with revised allowances ended after 235.10 s / 9
completed calls / 25718 reported tokens: its last completion returned zero native
tool calls despite forced selection. No text fallback was executed; rollback left
zero changed files. Evidence: `/tmp/bigbrain-maintenance-campaign-pm55ki_c`.
The old diagnostic did not retain finish_reason, so token exhaustion cannot be
claimed as the precise cause; subsequent errors retain that field. Short-mode
local trials with corrected protocol feedback completed below. No original G-code
repair so far. Latest full local suite: 1189 passed / 9 warnings (147.29 s).
The independent reviewer now has distinct inspection and final-decision schemas,
rejects repeated identical pages early, and can correct unsupported evidence IDs
within a bounded budget. A proposed pass with no executed evidence is downgraded
to `needs_evidence` with the exact approved criterion; it is never upgraded to a
pass. The rejected verdict remains in the diagnostic. Tests cover fabricated IDs,
absent assertions, decision-phase bounds and fail-closed behavior.

Two short-mode local trials passed after this protocol work. The standalone trial
used 109.89 s / 24 calls / 40612 tokens; only main.py and runtime metadata changed.
Its CLI coverage remains indirect (source inspection plus function test, no
dedicated subprocess assertion); passing the reviewer is not proof of exhaustive
acceptance coverage. Evidence: `/tmp/bigbrain-maintenance-campaign-flmg0ncb`.

Frozen Mistral comparison (one sample per path; not a statistical benchmark):
`/tmp/bigbrain-maintenance-campaign-vx_136uy`, ordinary reasoning `none`.

| Case | Previous creation DAG | Maintenance loop |
| --- | --- | --- |
| Local | Planning rejection; 41.51 s / 4615 tokens | Delivery accepted; 61.13 s / 21460 tokens |
| Cross-module | Planning rejection; 21.68 s / 5369 tokens | Independent review inconclusive; rollback; 154.19 s / 60868 tokens |
| Contradictory test | ArchitectureConflict; 30.88 s / 5375 tokens | Correct explicit arbitration, no source changes; 30.11 s / 8063 tokens |
| Missing environment | Planning rejection; 16.58 s / 4639 tokens | Action budget exhausted without preparing environment; rollback; 163.17 s / 55846 tokens |
| Large selective context | Planning rejection; 43.07 s / 62377 tokens | Independent review inconclusive; rollback; 156.47 s / 53660 tokens |

G-code on the same candidate failed to deliver: 203.37 s / 41 calls / 200625
tokens, action budget exhausted after repeated list/read actions. No patch was
made; rollback completed and original source hashes matched. Evidence:
`/tmp/bigbrain-maintenance-campaign-o6kbn1e6`. This is a real negative competence
result, not an infrastructure credit failure and not a reason to lower the gate.
No immediate G-code retry was started.

### Explicit runtime state and unrestricted local thinking (2026-10-23)

User requested an explicit state of reads, diagnostics and blockers, plus high
reasoning without a local thinking-length cap. `MaintenanceState` now owns these
facts rather than the model notebook. Every action context carries paged exact
inventory names, read hashes/merged line ranges/next unread line, stale coverage,
source epoch, diagnostic status/failing case IDs/environment, environment setup
status, failed verification stages and unresolved tool/precondition blockers.
Preparing an environment does not grant patch permission: an actual passed or
failed diagnostic is still required. A new successful diagnostic clears the
specific diagnostic-required blocker. Patches invalidate affected read coverage
and mark previous diagnostics as belonging to an older source epoch.

`state_read` pages older/remaining metadata; `diagnostic_read` retrieves full
recorded results by observation ID. Full metadata snapshots are content-addressed
artifacts after every recorded step. Prompt snapshots do not inject whole source
files or all diagnostics. Model notebook text cannot modify these runtime facts.
Tests cover persistence beyond the last four observations, paging, range merging,
version invalidation, blocker resolution, missing environment and malformed review
output. This is per-run state, not a replacement for the shared-memory branch.

Studio Large 4 now defaults to `reasoning_effort=high` (explicit env override
`none` remains available). High requests omit `max_tokens` entirely, including
contract drafting and tool calls; the former small completion budgets no longer
starve the final answer after thinking. No per-call HTTP read or reasoning-stage
timeout applies in this mode; connection establishment is still bounded at 10 s.
The maintenance task still has its advertised 40-action / 600-second outer bound
and cancellation/rollback. Provider context/output limits still exist: this is
not infinite reasoning or spending. A provider `finish_reason=length` fails
explicitly instead of accepting a partial answer, also for streaming responses.

First new high/state trial reproduced the bug, patched and verified, then the
review request hit HTTP 400 (33.46 s / 5 calls / 8708 tokens). A minimal live
probe confirmed `top_p must be 1 when using greedy sampling`. High Studio
requests with temperature zero now explicitly send `top_p=1`. This is API
compatibility, not a relaxed acceptance gate. That follow-up (205.89 s / 21 calls /
53144 tokens) reproduced and repaired the defect, then added a new CLI regression
test in response to the independent review; the new test passed. Delivery still
failed because the independent reader returned a flattened action and its parser
raised AttributeError. Transaction rolled back. Evidence:
`/tmp/bigbrain-maintenance-campaign-6ibt4u7d`. Malformed reader action/coverage
shapes now receive bounded schema feedback without executing them or accepting
their claims; a regression test covers recovery and unread-source protection.
Final full local gate: 1200 passed / 9 existing warnings (146.33 s).
The follow-up completed unsuccessfully: `/tmp/bigbrain-maintenance-campaign-6i9ti8lq`.
It reached the 600 s maintenance budget (627.45 s including planning), with
18 completed calls / 95072 provider-reported tokens. The patch was rolled back,
with no transaction conflict or retained source changes. High reasoning did not
establish delivery on this small case.
The completed G-code and
low-reasoning comparisons above predate this runtime-state/high profile; do not
reuse them as competence evidence for the new configuration.

Primary contracts: [reasoning](https://docs.mistral.ai/studio/conversations/reasoning),
[function calling](https://docs.mistral.ai/studio/conversations/function-calling).

## Completion audit (not a completion claim)

### Codex subscription probe (2026-10-23, not a model competence result)

User requested the same local disposable case with `gpt-6.1-sol` through the
ChatGPT subscription, then explicitly selected **low**, not high. The installed
application binary is `/usr/lib/chatgpt/resources/codex` (0.163.0-alpha.10.2);
it is not on PATH. `login status` and `account/read` confirm ChatGPT authentication;
`model/list` includes the exact requested model (catalog membership alone is not
proof of inference access).

The connector needed compatibility work: current text input, structured output
schemas, named permissions, notification filtering, reported usage, terminal
failure handling, cancellation and owned-child shutdown. Low is the default;
no API fallback is allowed. Codex receives an empty inference directory rather
than the project checkout; BigBrain remains responsible for project tools.
An autonomous Codex tool-start event invalidates the trial. The corrected
transport is live-validated on the local case below, not yet on the G-code case
or all application roles.

The initial campaign `/tmp/bigbrain-maintenance-campaign-ricg2cj5` stopped before
any completion with a capability-negotiation error hidden by the contract
drafting fallback (summary: ValueError, zero completed calls). After protocol
negotiation corrections, both a high probe and low probes failed before model
output with `failed to load workspace requirements`.

Root cause isolated by comparison with the documented minimal thread: our custom
permissions profile was declared without `default_permissions`. The standalone
configuration validator exposes the precise error: `config defines [permissions]
profiles but does not set default_permissions`; the turn bootstrap masked it as
a workspace requirements failure. Adding the matching default preserves the
same restricted profile. A strict `{"ready":true}` live probe then succeeded in
low reasoning, with no credential reconnection or permission expansion.

The first maintenance retry (`/tmp/bigbrain-maintenance-campaign-gpgb179q`)
drafted its contract but failed at the action schema: Codex strict output
requires every property to appear in `required`. The adapter now represents
originally optional properties with nullable transport slots and removes only
those absent-value placeholders before dispatch. Original required/nullable
fields, enums, numeric bounds and closed-object constraints remain intact;
caller schemas are not mutated. This uses strict structured arguments, not
native function-call transport, unlike the Mistral/OpenRouter adapters. The
business runtime and verification gates are unchanged. Private campaign errors
now retain RuntimeError diagnostics rather than reporting only their class.

The corrected low trial completed successfully in
`/tmp/bigbrain-maintenance-campaign-b4psdhvh`: **176.98 s / 22 completions /
219841 reported tokens (216095 input, 3746 output)**. Twelve maintenance actions
reproduced the defect and minimally patched main.py. The first independent
review requested missing executable CLI evidence; the worker added a separate
CLI regression suite and reverified. The project interpreter executed **12
passing tests**; syntax, compile, run, contracts, tests, source_revision and
independent semantics all passed. Transaction committed, no conflicts. Only
main.py, two new regression-test files and the runtime manifest changed; the
existing test_main.py is byte-for-byte unchanged. No original
G-code project changed, no API billing fallback used, and no merge performed.
The fixture approval remains synthetic. This single small case is not broad
reliability evidence, and does not isolate model quality from transport/profile
changes. Codex context overhead remains significant; reported tokens are not a
dollar cost or a measurement of subscription credits. Earlier diagnostic probes
are not included in this trial's usage count.

Final gate on corrected code: **1206 passed / 9 existing warnings (145.58 s)**;
13 targeted connector tests included. No UI changes in this follow-up.
Do not count earlier transport failures as evidence against Sol or claim zero
subscription consumption from missing usage.

Protocol references: [App Server](https://learn.chatgpt.com/docs/app-server),
[permission profiles](https://learn.chatgpt.com/docs/permissions).

| Requirement | Authoritative evidence / remaining limit |
| --- | --- |
| Dedicated loop, scoped approval and event lifecycle | `test_existing_project_plans_maintenance_without_guessing_files`, `test_bus_approval_dispatch_live_progress_and_terminal_commit`; actual bus, scripted model |
| Progressive large-project inspection | `test_progressive_reader_handles_large_projects_without_source_dump`; live native large-project delivery still pending |
| Revision checks, concurrent edits, Stop and rollback | `test_dynamic_journal_rejects_stale_reads_and_rolls_back`, `test_concurrent_user_change_and_fencing_are_not_overwritten`, `test_cancellation_does_not_swallow_stop_or_commit` |
| No unapproved test weakening / no worker-declared success | `test_validation_is_not_an_unapproved_repair_surface`, `test_new_regression_tests_allowed_but_existing_tests_stay_frozen`, `test_loop_cannot_claim_success_or_weaken_tests_and_failure_rolls_back` |
| Project Python, environment failure and bounded diagnostics | `test_real_cross_module_repair_project_python_review_and_commit`, `test_missing_environment_is_inconclusive_not_a_patch_license`, `test_excessive_test_output_is_inconclusive_and_terminated` |
| Separate web specialist with actual preview/browser checks | `test_web_specialist_repairs_actual_browser_behavior`; model scripted, browser real |
| Independent evidence-based review | `test_progressive_reviewer_cannot_cite_unread_sources` plus successful native live cross-module review; not exhaustive domain verification |
| Preserve creation / explicit routing | Full regression suite, legacy baseline in `test_project_modification.py`, native-route tests; no keyword routing added |
| Real G-code repair and complete old/new competence comparison | **Not achieved**: deterministic G-code checks passed once, independent review did not finish; later provider interruption. No final success claim or merge |
| Automatic recovery of imported legacy metadata | **Not demonstrated by campaign**: fixture metadata supplied explicitly; not interchangeable with the real user workflow |

## Provider protocol

Codex integration follow-up: stable account/conversation/agent threads, suffix
inputs, restart/resume, native manual/automatic compaction and usage deltas are
implemented. Bounded live multi-turn probe passed; final gate 1217 tests passed.
Details and limits: [Codex conversations](CODEX_CONVERSATIONS.md). The 22-call
repair campaign above predates this integration. Orchestration redesign remains
a separate discussion; no new full repair campaign or G-code success claim.

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

### Orchestration follow-up

See [MAINTENANCE_ORCHESTRATION.md](MAINTENANCE_ORCHESTRATION.md) for automatic
preflight, explicit states, grouped reads/patches, automatic verification and
size-bounded independent review. These replace compulsory per-file round trips
without weakening approval, source integrity, test protection or acceptance.
The paired tiny-case live result and its cache/latency limits are recorded there.
The subsequent runtime baseline, structured missing-evidence requests and
versioned worker event context are implemented and checked offline. They have
not yet been measured in a new live run or validated on the real G-code copy.

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

## Validation checkpoint — 23 October 2026

Full offline suite after budget reservation: 1269 passed / 9 existing warnings
(159.08 s); 74 focused maintenance/usage/budget checks passed.
The pinned disposable candidate passes six executable stages (64 project tests,
19 subtests), but independent acceptance remains inconclusive. Two bounded
review-only attempts exhausted their token budget without a verdict. The latest
attempt used eight Sol 6.1 low calls, 161260 reported tokens (133120 cached).
Incremental review delivery is confirmed live: only new observations are sent,
not overlapping snapshots. Original project unchanged; no merge authorized.
Review budget reservation is now implemented offline. Each independent review
captures task-local provider usage, avoiding other conversations' consumption.
Default local bounds are 20 calls, 150000 reported tokens and 300 seconds;
an outer campaign can publish tighter remaining limits. Before each call the
runtime exposes remaining capacity. It forces a decision-only schema when two
calls remain, 45 seconds remain, usage is unknown, or the remaining tokens are
below twice a conservative decision allowance (last input + maximum source page
+ output allowance). The allowance is an estimate, not billed usage or a hard
token ceiling. In-flight calls can overshoot; time is bounded by remaining time.

Budget pressure cannot approve unread tests or weaken criterion coverage. A
needs-evidence/arbitration verdict can be returned without inspecting every
source; only a pass requires implementation and actual test assertion inspection.
Final budget decisions do not trigger automatic baseline/diagnostic fetching.
Unknown usage triggers conclusion rather than unlimited reads. No paid rerun
after this change yet; independent candidate acceptance remains unconfirmed.
