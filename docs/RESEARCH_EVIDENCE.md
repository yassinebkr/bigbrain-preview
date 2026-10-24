# Research evidence runtime — phases 1 to 4

Current acquisition/context status: phases 3/4 are implemented and validated
offline; phase 5 connects their observed states to the existing Atelier. See
[`RESEARCH_ATELIER.md`](RESEARCH_ATELIER.md) for current integration, validation
and the next-branch boundary. Historical test counts below describe earlier
snapshots, not the current full suite. Real-web semantic acceptance remains open.

Acquisition/context sub-plan update, 24 October 2026: the phase-3 reader supersedes
the initial HTTP-only implementation described below. It adds source-aligned
structured extraction, original observation artifacts, cache and explicitly
requested bounded browser reads. See [`RESEARCH_ACQUISITION.md`](RESEARCH_ACQUISITION.md)
for current limits and tests. Older HTTP-only/unsupported-JavaScript statements
below describe the earlier implementation, not the current acquisition path.

Implemented on `feat/research-evidence`, 24 October 2026. No paid or live
research campaign has been performed. Phases 3/4 have resumed after the demo
incident fixes were pushed separately as `3f458b3`; their implementation is
under offline validation, not live-provider or browser acceptance.

Resumed regression: 1,411 Python tests passed (9 warnings, 170.95 seconds),
including 64 focused research tests; 120 UI tests passed and production build
succeeded. No paid-model research assessment has been run.

Offline validation: complete Python suite 1,372 passed / 9 warnings (168.56 s).
Five additional runtime cases and the final schema/diagnostic changes were
covered by a subsequent focused run: 80 passed / 5 warnings (4.21 s).
No UI files changed; no claim of browser/live provider validation is made.

## Contracts and entry point

`bigbrain/research.py` defines strict schema version 1.0 contracts for questions,
sources, passages, claims, evidence links, actions, observations and research
state. Unknown fields fail validation. `ResearcherBrain` invokes this runtime
through its existing task/result envelope and emits action/observation progress
through the existing bus. The returned `evidence` object contains the full record.

The model first proposes a plan with question IDs, required evidence and a
freshness justification, then chooses search/open/conclude/clarify actions.
Only discovered source IDs can be opened. Successful page reads produce passages
with source IDs, consultation time, body hash, final URL and truncation flag.
Publication/author fields remain unknown unless established; consultation time
must not be mistaken for publication time. Failed reads never create passages.

Claims must cite existing passages and reference a valid question. Without a
successful separate assessment they remain `unverified`: collection alone is
not a verified conclusion. No model
confidence, lexical agreement score or domain-count truth score is emitted.
References prove that a passage was read, not that it entails the claim.

## Execution and access boundaries

Default limits are 12 actions, at most 5 searches as configured by the worker,
6 page attempts and 90 seconds total. These are runtime limits, not model-supplied
permissions. Policy calls and reads are inside the total timeout. Repeated
searches/reads are blocked. Cancellation propagates as cancellation. No automatic
retry occurs after malformed policy output; the partial record explains why.

The page reader supports public HTTP(S) HTML/plain text on ports 80/443. Every
redirect is checked again. DNS results must all be public; connections use the
validated IP with original Host and TLS SNI, avoiding a second DNS lookup.
Credentials and environment proxies are excluded. Bodies are capped at 1 MB;
extracted text is capped at 12,000 characters per page. PDF, JavaScript-rendered
pages and authenticated sites require later adapters and report limitations.

Visible-text extraction excludes scripts/styles. Remaining page text is still
untrusted data; prompts do not grant it authority. The runtime validates actions
and citations even if a model follows an injected instruction. Semantic relevance
and resistance to misleading natural-language claims require phase 3 evaluation.

Search empty, search error, inaccessible page and missing provider are distinct.
Without a model, DiscoveryPolicy searches the original question, reads discovered
pages within limits and returns evidence without inventing a factual synthesis.
No year/latest suffix is appended. Existing `search_only` remains discovery only.

## Offline reference corpus

`tests/test_research_runtime.py` contains frozen public-style artificial passages:
stable concept, version-specific docs, contested primary assertion, circular copy,
isolated testimony, reproducible blog, reputed unsupported claim, obsolete page,
irrelevant content and prompt injection. Expected properties are runtime gates,
not generated LLM verdicts: text is preserved, snippets are not read evidence,
source type stays unassessed, and no verified claim is fabricated.

Additional cases cover failed access, empty vs failed discovery, invalid citation,
valid citation with unverified status, missing source, repeated action, timeout,
budget exhaustion, cancellation, unsafe targets and the actual worker envelope.
This is a phase 1/2 reference corpus, not proof of phase 3 fact-checking quality.

## Laya adapter boundary

`Policy.choose(state, remaining)` receives a snapshot and proposes a typed action.
ResearchRuntime owns tools, observations, citations and limits. This follows the
Planner/Policy/Environment separation inspected in `near_agi` revision `bfc6286`.
An optional candidate proposer/transition predictor can later sit behind Policy;
it cannot manufacture observations or fact-verification outcomes. No Laya
checkpoint is loaded and simulator-to-web transfer is not assumed.

## Phase 3: inspectable evidence assessment

`research_assessment.py` separates review from the search policy. Each read
source must be considered for every proposed claim, including counterevidence.
Exact observed quotations are mandatory. Source suitability, nature, claim
scope and missing evidence remain explicit; unknown is not false. Copied text,
canonical redirects and observed attributed origins are grouped conservatively;
different domains alone never establish independent corroboration. An optional
`assess` action lets the policy inspect missing evidence before concluding;
subsequent page reads invalidate the previous assessment. At most two reviews
are allowed. Semantic entailment remains a model judgment, not objective truth.

## Phase 4: observable and retained research

The Atelier research surface shows questions, the current action, found versus
read pages, source assessments, conclusions, exact quotations, limitations and
observed actions. Versioned snapshots and actual passage observations travel
through the bus and run history. Research IDs distinguish retries; run/session
correlation prevents cross-conversation updates. Duplicate or stale snapshots
are ignored. Stop retains terminal evidence without resurrecting execution.
After restart, interrupted work is displayed honestly; no automatic execution
resume is implemented. Usage distinguishes reported tokens/cost from unknown
usage and conservative allowance reservations; this is not exact billing.

## Remaining milestones

Finish full regression and real browser acceptance of phases 3/4. Phase 5:
authorized live comparison, including usefulness, noise, evidence quality, cost
and latency. A configured Brave key is not itself a successful live validation.

Integration smoke test on 24 October: one real Brave query for public Python
`pathlib` documentation returned two results; the public page reader fetched
`https://docs.python.org/3/library/pathlib.html`, retained 12,000 characters and
a content hash. No LLM call or user memory was used. This validates search/read
connectivity only, not semantic review quality. UI regression: 120 tests passed
and the production build succeeded. An attempted browser check at port 3007
showed an OpenClaw gateway authentication screen, so the current Atelier was
not accepted visually through that browser target; no credentials were entered.

Exact token/cost accounting and calibrated stopping quality remain future gates;
action/time/page bounds and conservative token allowances are implemented.
The full-stack feature discussion stays deferred.
