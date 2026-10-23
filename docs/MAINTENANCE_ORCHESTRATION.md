# Maintenance orchestration

Implemented scope (2026-10-23): deterministic preflight, grouped evidence and
patch sets, automatic verification, and size-bounded independent review.
Creation DAGs, UI layout and shared-memory policy are unchanged.

## Execution contract

- An approved immutable contract and bound existing-project transaction are
  required before preflight. The specialist diagnostic callback executes before
  the first model turn, with the existing source/test integrity checks and
  project-environment policy. An unavailable environment does not authorize
  patching. Successful environment preparation automatically reruns diagnostics.
- Runtime facts include an explicit phase: diagnosing, investigating, blocked,
  correcting, verifying, validated, not_delivered or cancelled. Progress events
  carry the phase; evidence stores terminal state. These are runtime facts, not
  claims about model thinking. No new UI animation is claimed here.
- `read_many` supplies 1–8 source pages in one model observation. Each page uses
  the existing 200-line / 14000-character limit; aggregate content is at most
  48000 characters and encoded pages at most 64000 characters. No silent
  aggregate truncation. Invalid/over-budget requests do not mark pages read or
  grant new revision hashes. Large sources remain selectively accessible.
- `patch_set` accepts 1–8 distinct files and at most 128000 encoded bytes. All
  fragments, paths, syntax, read hashes and protected-test permissions are
  validated before any write. Application rechecks revisions. Any application
  failure aborts the maintenance run; the enclosing transaction owner restores
  recorded writes or preserves concurrent edits as a conflict. This is not an
  OS-level atomic filesystem transaction or a rollback of arbitrary side effects.
- Legacy single-file patches remain supported and follow the same validation
  and automatic verification path. The model no longer needs another turn to
  request checks after applying a correction. It can still request diagnostics
  and verification without edits when evidence requires them.
- Only successful mandatory verification can declare delivery. A repeated
  identical actionable verification failure at the same runtime source epoch
  stops the run instead of consuming the whole action budget. The comparison
  excludes incidental artifact IDs and timings, but is not a general semantic
  detector of equivalent model hypotheses. Existing time/action limits remain.

## Independent review

The independent review scope, actual source revision and acceptance requirements
are unchanged. When the complete pinned source set contains at most 16 files
and 48000 UTF-8 bytes, the runtime supplies it together and requests a verdict
directly. This removes compulsory per-file read turns, not source inspection or
the need to cite executed evidence. Missing assertions still yield needs_evidence;
contradictions and unknown domain semantics still require arbitration.

Larger source sets retain the selective, paged review loop. No keyword/domain
heuristic selects which acceptance criteria to ignore. The reviewer does not
inherit the worker's conversation or treat its notebook as proof.

## Verification and limits

Offline tests cover automatic preflight, unavailable environments, grouped
evidence delivery and bounds, stale revisions, protected tests, invalid syntax,
duplicate paths, partial apply failure with owner rollback, automatic final
verification, repeated failure, cancellation, large-project selective inspection,
and compact review rejecting fabricated or missing evidence.

Final offline gates: **1231 passed / 9 existing warnings (155.20 s)**, including
46 targeted maintenance/state tests (11.44 s). Syntax compilation and
`git diff --check` also pass. No UI sources changed; no new UI build claimed.

Scripted providers test runtime decisions, not model competence. The existing
real project-interpreter and browser fixtures remain applicable. The following
authorized live comparison is separate from that offline evidence.

## Point 4: paired live probe (2026-10-23)

User explicitly authorized point 4. Private evidence:
`/tmp/bigbrain-orchestration-pair-rirx71vm`. Opt-in launcher:
`tools/compare_maintenance_orchestration.py --live`.

Both use the current Codex subscription adapter, GPT-6.1 Sol low, fresh isolated
session directories, one persistent worker thread per variant and a separate
scope per independent review invocation. Before loads only maintenance/state/
progressive-review implementations frozen at `79d9cfe` into the harness process;
it does not overwrite the working tree. After uses the current implementation.
Both start with the identical two-file twice(n) fixture and three fixed criteria
from the previous probe: numeric doubling, CLI preservation, existing tests plus
regression coverage. No model-generated contract differences. Each project has
its own Python 3.12.13 environment; the offline harness deliberately exposes the
same installed test dependencies through a .pth file, not a production fallback.

Shared ceilings: 24 attempted calls, 300000 reported tokens checked before the
next call (soft limit), existing 600-second runtime budget. Neither reached a
limit. Approvals are synthetic harness approvals, not a live UI validation.

| Metric | Before | After |
| --- | ---: | ---: |
| Final independent verdict | passed | passed |
| Calls (worker + reviewer) | 11 (7 + 4) | 5 (3 + 2) |
| Input tokens | 130531 | 54648 |
| Cached input (subset of input) | 96768 | 9728 |
| Input not reported cached | 33763 | 44920 |
| Output tokens | 1692 | 2104 |
| Reasoning output (subset of output) | 0 | 128 |
| Total reported tokens | 132223 | 56752 |
| Wall time including cleanup | 62.528 s | 59.681 s |
| Final executed project tests | 7 | 12 |
| Existing test file unchanged | yes | yes |
| Transaction | committed, no conflict | committed, no conflict |

All seven gates passed: syntax, compile, run, contracts, tests, source revision
and semantics. Both final main.py files equal the original except `return n + 2`
becoming `return n * 2`. Before creates one regression file; after creates two.
Runtime publishes the .project.json manifests. No human repair or intervention;
the original G-code project is untouched.

After grouped its initial reads and its first implementation/test patch. Its
first independent review requested original-CLI evidence; the worker added
baseline-comparison assertions for five argument combinations, then a fresh
review accepted. A read-only AST audit confirmed that the baseline literal in
this test exactly matches the frozen original, not an invented substitute.

One usage record per completed call reconciles exactly with the aggregate;
every record names the requested model, no incomplete-counter flag or compaction
was observed. Raw synthetic prompts/replies, hashes, contract, scoped bindings,
gate results and transaction journals remain in the evidence directory.

This pair has **54.5% fewer calls, 57.1% fewer reported tokens, but only 4.6%
less wall time**. It does NOT establish lower subscription cost: uncached input
is higher after (44920 vs 33763), cache rates differ, and no subscription-credit
or dollar conversion is established. One sequential pair has order/cache/model
variability; different generated test counts are outcomes, not changed input
acceptance. This validates the tiny case, not G-code/complex-project reliability.
The older 219841-token ephemeral-thread run is not the paired baseline.

Three additional offline harness tests pass: explicit live opt-in, frozen
acceptance and baseline substitution/restoration on failure. Run separately
from the earlier 1231-test full gate; no new full-suite total is claimed.
Native thread/usage protocol: https://learn.chatgpt.com/docs/app-server

## Runtime provenance and event context follow-up (2026-10-23)

The paired probe exposed a missing original-CLI reference and repeated worker
snapshots. The following changes are implemented locally after that probe; its
token/duration numbers do not measure these new changes.

Before diagnostics or edits, maintenance captures the permitted source inventory
as a content-addressed baseline and checks its hashes against the frozen revision.
The original diagnostic is separately stored with the source hashes it executed.
Review validates those artifacts, candidate hashes and revision identifiers.
Small source sets include before and after sources together; larger ones expose
bounded `read_baseline` pages and character-paged `read_diagnostic`. The review
envelope includes a bounded diff preview, changed-path counts and revision hashes.
Truncation is explicit; source tools remain available. Baseline literals written
by the worker do not establish original-source provenance. No original-code
execution or extra environment provisioning is introduced by baseline capture.

Missing evidence requests now contain criterion_id, kind, path, source_revision
and request. Wrong criteria, paths or revisions fail closed. Available baseline
or initial diagnostic evidence is resolved within independent review before
asking the worker for another patch. This resolution does not upgrade a verdict
to pass. Behavioral gaps still need relevant executed assertions. Fresh free-text
requests are rejected; old stored journal text remains readable. Missing source
evidence is not reclassified as a behavioral test failure.

Codex workers opt into `maintenance-events/1`: immutable initial contract/run
identity followed by numbered observations and changed runtime-state fields.
Grouped-read contents travel once. Each event has an immutable artifact and
source epoch; full diagnostics stay accessible without nested JSON strings or
duplicate traceback aliases. The provider's persisted message cursor sends the
unseen batch suffix. A failed submission before native acceptance does not
advance it. Other providers retain self-contained bounded snapshots.

After an observed native compaction, the next maintenance call supplies a current
authoritative checkpoint. This also works when the provider resumes after a
restart. It does not promise lossless native summaries during a compaction inside
the current inference turn, nor resumption of an interrupted Python maintenance
coroutine after a server crash. Existing transaction recovery remains necessary.
The persistent native history still contributes to input usage. No new token,
latency, cost or G-code success claim follows from offline tests.

Validation covers artifact substitution, stale candidate revision, structured
request binding, stored-baseline resolution, real runtime capture, unique durable
events, grouped-read delivery, stateless context, retry and compaction/restart.
Final regression: **1248 passed / 9 existing warnings (151.08 s)**; targeted
maintenance/provenance/conversation checks: 64 passed (11.24 s). Compilation and
`git diff --check` pass. No new live
inference, original-project mutation, commit, push or merge in this follow-up.

## Disposable G-code probe after user authorization

Private evidence: `/tmp/bigbrain-gcode-events-_gj98u39`; report:
`../../tests/bigbrain-gcode-probe-2026-10-23.md` in the sibling tests workspace.
This run was interrupted before any patch was applied. Native inference proposed
the two already-authorized test corrections, but mutable nested state changed
previous event batches and caused replay. The resulting input also exposed the
64 KiB default asyncio JSON-RPC line limit; a dead reader could strand an active
turn and shutdown. Runtime state now deep-copies event data; transport frames are
bounded at 8 MiB, reader failures wake active turns and shutdown drains the pipe.
Offline regressions reproduce nested mutation, large frames and dead-turn exit.
Final full regression: **1252 passed / 9 existing warnings (152.26 s)**; syntax
and diff checks pass. No live run has tested these corrections yet.

Transaction rolled back; all seven copied sources match the original. No review
or final verification ran. One planning and four worker calls consumed **116075
native-reconciled tokens**, including 42923 missing from the interrupted
application ledger. Cache: 67840 input tokens; input 114522, output 1553. No
subscription-cost claim. These counters and evidence are separate from the tiny
paired probe and from subsequent offline fixes.

## Reproducible offline replay and generic campaign controls

`tools/replay_maintenance_trace.py` replays selected saved replies through a real
local stdio subprocess and the normal provider/runtime stack. It cannot call a
model. The archived patch is applied and real verification finds one remaining
assertion tied to the literal word "not" versus actual "never a measured
temperature". Replay ends when the recorded worker continuation is exhausted;
no missing review or follow-up response is invented. This is not a delivered
G-code project. Separate cross-module fixtures exercise successful verification
and commit, real bus proposal/approval/dispatch, and transport EOF with rollback.
Synthetic review responses establish protocol behavior only. No domain-specific
success shortcut was added to the runtime.

The live campaign launcher now isolates session roots before provider creation,
logs calls before dispatch, retains per-phase usage and failures, and stops on
unknown usage or bounded calls/tokens/time. --contract-file deliberately skips
contract generation for one frozen maintenance fixture. Original UI/planning
approval is outside that fixture's claim. Reference report:
`../../tests/bigbrain-maintenance-replay-results.md`.

Full offline regression: 1257 passed / 9 existing warnings (150.71 s), plus eight
targeted replay/comparison checks after frozen-contract support. No inference is
performed by the new replay tests. A single subsequent authorized live run is
recorded separately in the report; no merge before user validation.

The live continuation completed without a transport stall (7 worker calls,
221122 tokens, 79.186 s). Project diagnostics passed 64 tests/19 subtests, but
the new frozen-contract fixture omitted user_request in its subtask, so the
approved-request gate correctly blocked final verification. This harness field
is corrected; runtime maintenance additionally checks request identity before
diagnostics/inference, independent of project domain. A frozen cross-module
commit regression and mismatched-request zero-call tests cover this boundary.
Corrected offline replay of those exact live responses passes six executable
stages and stops at the unavailable independent review. No synthetic review is
presented as live acceptance. Report/evidence distinctions are documented in
the referenced results file. No further paid retry in this step.
Final regression after the early-binding guard: **1260 passed / 9 existing
warnings (160.09 s)**; 61 focused checks passed. Candidate/evidence pointers for
review-only continuation are saved in the sibling tests workspace's
`bigbrain-maintenance-review-checkpoint.json`. Independent acceptance remains
pending; the frozen-candidate replay must not be reported as a live review.
