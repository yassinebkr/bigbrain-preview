# Research efficiency: phases 1–4

## Compact documentary default

Current acceptance gates and the expanded worker journey matrix are specified in
[RESEARCH_ACCEPTANCE.md](RESEARCH_ACCEPTANCE.md). HTTP acquisition can upgrade a
JavaScript-required observation within its separate browser allowance, including
after HTTP capacity is exhausted. Native Codex raw-event monitoring is requested
for fresh threads; resumed visibility and tool-free generation remain acceptance
limits. No transport migration or automatic provider fallback was introduced.

The default model-driven worker collects passages and concludes directly, with
six decisions, three searches and four reads. One independent review is available
for explicit review requirements, policy-identified high stakes, contradictory
evidence or independent-corroboration questions. Recorded review requirements
persist across continuation. Injected reviewers retain the strict path.

Documentary findings preserve `unverified` claim status and `unassessed` answer
status. The runtime validates citation identity and read-source observation hashes.
The Atelier labels documentary synthesis and independent-review requirements.
Completed task status describes synthesis delivery. Remaining gaps keep results
partial. Live quality and measured efficiency remain acceptance gates.

See `../../tests/research-efficiency-evidence/DOCUMENTARY_PATH.md` for validation
and the API Anything source-adapter reference confirmed by the user.

Implemented 25 October 2026 on `feat/front-decision-v1`, without switching or
merging the pre-existing dirty branch. This is offline implementation evidence,
not acceptance of fresh live research, model reasoning or browser UX.

## Reference and gates

`tests/research_efficiency_benchmark.py` reuses the seven manually annotated
research corpus cases: long versioned documentation, article, table/code,
JavaScript shell, copied sources, contradiction and blocked access. It runs the
actual reader, extraction, runtime and policy prompt/schema assembly. HTTP and
model responses are local fixtures/scripted decisions. No external inference,
network or monetary-cost estimate is involved. Three samples per case.

The reference preserves source/manifest hashes; raw reports and pre-change
research sources are in `../../tests/research-efficiency-evidence/` in this
workspace. Reproduce the current serial/grouped comparison with isolated roots:

```bash
BIGBRAIN_EVIDENCE_ROOT=/tmp/research-serial PYTHONPATH=. .venv/bin/python tests/research_efficiency_benchmark.py --output /tmp/research-serial.json
BIGBRAIN_EVIDENCE_ROOT=/tmp/research-grouped PYTHONPATH=. .venv/bin/python tests/research_efficiency_benchmark.py --grouped --output /tmp/research-grouped.json
```

Gates: critical omissions must not increase; no invented/blocked evidence;
independent multipage cases must require fewer decisions and serialized request
bytes. Live token/latency/semantic gains require a separate authorized evaluation.
The corpus is known; it is not an unseen semantic holdout.

| Mechanical metric | Pre-change serial | Candidate grouped |
|---|---:|---:|
| Policy decisions, seven cases | 24 | 21 |
| Decision state bytes, cumulative | 39,339 | 31,557 |
| Prompt + tool schema bytes, cumulative | 216,835 | 191,512 |
| Copied-source case decisions | 5 | 3 |
| Contradiction case decisions | 4 | 3 |

State bytes decrease 19.8%, complete serialized requests 11.7%. Single-page
requests become slightly larger; savings are concentrated in multipage work.
Bytes are not tokens. Local extraction timings are descriptive, not estimates
of remote-model latency. Both scripted runtime variants miss the rendered-only
JavaScript fact; the omission is recorded, not presented as success. The separate
rendered-input selection experiment is not evidence of runtime browser use.

## Grouped collection and bounded context

`Action.batch` contains at most four independent `CollectionRequest`s. The
runtime validates every child and aggregate search/page/browser budgets against
the pre-batch discovery state before starting I/O. A batch cannot discover an ID
and open that new ID in the same group. Default concurrency is three, maximum
four, with one active request per hostname (search-provider calls serialized).
Existing public-network, browser escalation and blocked-access rules remain.
Siblings are cancelled and awaited on deadline, cancellation or task failure.

Each completed child is checkpointed and emitted immediately. An interrupted
batch retains actual completed observations; unstarted/unfinished siblings do
not acquire fabricated outcomes. URL fragments do not create duplicate sources.
Search/page/browser counters count operations, not just grouped decisions.

Policy state has an 18 KB serialized ceiling. Complete heading packets and
pinned citations are preserved; omitted IDs are explicit and originals remain
available. Required citations/metadata that cannot fit fail explicitly rather
than clipping a quotation. Navigation/history are bounded independently.
Unused native schema definitions/titles are removed without removing execution
validation. Per-call records include phase, outcome, duration, known/unknown
usage, input/output/cache tokens and known/unknown cost. Tool observations retain
their execution duration; previous attempt usage is kept separately.

## Explicit continuation

`ResearchInput.resume_research_id` is selected by the front model, not inferred
by keyword matching. A small conversation-owned research index gives IDs,
objective excerpts and coverage gaps; it does not inject page contents or worker
transcripts. Changed scope starts a fresh task; ambiguous targets need clarification.
The runtime uses the stored immutable objective, not the conversational retry text.

Checkpoints live under `BIGBRAIN_EVIDENCE_ROOT/research/<owner-hash>/`, scoped by
workspace and conversation, with strict UUIDs, atomic replace, a 16 MB checkpoint
limit and nonblocking advisory leases. Leases release on process exit. Maximum
twenty continuations per research. A new attempt has a distinct ID, budget and
usage; revision and logical research ID continue monotonically. No restart
automatically executes work or consumes a new budget.

Retained reads older than five minutes, future-dated reads or reads with missing/
corrupted source artifacts are made non-citable until reread. Original history
is preserved. Changed observation hashes invalidate active old passages and
dependent conclusions; passage IDs are never reused for changed content.
Valid prior review is reusable only with identical questions, claims/citations,
sources and passages. Observed provider overhead floors survive continuation.

UI snapshots permit an explicit new attempt to become live without letting a
late event revive the same settled attempt. Batch passages appear immediately;
the journal projection retains their separate events. This is not a new UI design.

Existing pre-checkpoint research cannot magically be resumed by ID: it requires
a new run. Checkpoints contain research content and inherit evidence-root storage
policy; comprehensive deletion/retention/export remains an explicit follow-up,
not a claim that old evidence artifacts are erased with chat-history deletion.

## Selection and answer coverage

A bounded local heading-aware reranker was compared with existing section BM25
on identical original blocks. Required coverage and selected characters are equal
on this corpus; no gain was established. **BM25 remains the production default.**
This candidate is lexical/contextual, not a semantic model. No paid small-model
reranking or unseen semantic holdout validation was performed; adopting one
still requires measured benefit, including its extra inference cost.

Review now separates literal citation validity, individual claim support and
whole-question coverage (`QuestionAssessment`). An accurate claim can remain
supported while an uninspected version comparison leaves the question incomplete.
Question coverage must reference its own unique reviewed claim IDs. A model's
`complete=true` cannot override unverified claims or declared missing evidence.
Missing legacy coverage reports remain incomplete rather than silently complete.
The coverage judgment itself is semantic review evidence, not a mathematical
proof of truth or exhaustive page coverage.

The Atelier displays remaining question gaps. A reviewed run with incomplete
coverage is partial and retains useful supported claims; it is not advertised as
a complete answer. Exact citations, independent-origin checks and testimony/
general-claim distinctions remain enforced.

## Validation and remaining acceptance

### Closing-path control

The runtime exposes collecting, closing, reviewing and settled phases. Before
another collection decision, it forecasts the complete remaining review path,
including an optional corrective attempt. Native retained-context measurements
are shared between policy and review when they use the same provider instance.
Each call records its admission forecast, request sizes and any reported usage
above reservation. These forecasts guide admission; remote inference can exceed
an estimate, so the token limit remains an admission envelope.

When the full corrective path cannot fit, the runtime closes collection with a
single complete review if that path fits. Its committed review cap prevents a
subsequent corrective call. An invalid report then leaves the result partial.
Evidence requirements remain the same for either admitted path. The reviewer
generation schema includes the complete considered-source set and expected
claim/question identities, and the runtime validates citations and coverage.
Correction prompts retain observed evidence and the diagnostic; rejected reports
remain available as artifacts.

The local milestone report is
`../../tests/research-efficiency-evidence/CLOSURE_MILESTONE.md`. Three historical
admission replays close collection at decision three with observed sources retained;
198 focused tests pass. These replays simulate admission using historical actions
and usage. They establish neither a new semantic verdict nor measured live savings.

Live follow-up on 25 October: SQLite completed in 28.40 seconds; the Python
version comparison exposed a post-review reservation failure. Current review
identities now bypass redundant review assembly and reservation; changed evidence
still requires assessment. Failed attempts expose partial terminal answers while
preserving supported claims and their coverage audit. Per-call measurements now
include prompt/schema bytes and output reservation. The retained Python candidate
closes offline with zero extra model calls or reads; 147 focused checks pass.
The workspace report `../../tests/research-efficiency-evidence/REVIEW_CLOSURE.md`
records the reproduction and native usage diagnosis.
The fresh Python retest ended partial after 40.55 seconds and 104,554 reported
tokens. Its first review omitted a read source and the remaining envelope could
not admit correction. Native retained-history usage exceeded local reservation
estimates; source selection also failed to establish 3.13. Fresh acceptance
remains open. Full results are in the same workspace report.

Full repository suite: 1,566 passed, 8 optional tests skipped. Subsequent final
catalogue/type guards: 183 focused checks passed, including 20 efficiency tests.
Frontend: 132 tests passed and production build passed. Existing warnings remain;
git diff --check passes. Detailed failures and results are in the workspace report
at ../../tests/research-efficiency-evidence/REPORT.md.
New offline gates cover aggregate admission, bounded concurrency, cancellation,
partial-batch continuation, ownership, leases, stale/missing artifacts, changed
observations, worker continuation, compact context and question coverage.

Next steps are not implicitly started: phase 5 acquisition/extraction tool
comparison, then phase 6 authorized fresh real-web/end-to-end acceptance. No
Lightpanda, ScrapeGraph, ScrapingBee or Bright Data dependency was added. No live
claim of improved token billing, source-truth detection or full browser delivery.
Laya remains a future policy adapter over versioned observations/actions and
coverage/cost/latency traces; it does not replace runtime permissions or evidence.
