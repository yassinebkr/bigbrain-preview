# Research context selection — phase 4

## Conversational follow-up dispatch (2026-10-24)

The front model resolves references and retries against the current conversation
and emits a self-contained specialist query. Direct dispatch preserves that
query as the execution `user_request`, while `user_message` retains the raw turn
and `session_id` retains its conversation ownership. The task-routing label also
uses the resolved objective. Researcher input prioritizes explicit `query` over
legacy `user_request`, including envelopes produced before this correction.
No retry keyword detector rewrites the model's decision. Ambiguous references
are clarified by the front model. Offline regression reproduces the prior
overwrite and verifies front-to-orchestrator-to-researcher transmission with
both a retry and a continuation; live resolution remains part of manual UI
validation.

Implemented on `feat/research-evidence`, 24 October 2026. This is phase 4 of the
acquisition/context sub-plan. The extractor comparison and controlled acquisition
remain documented in `RESEARCH_ACQUISITION.md` and the frozen corpus.

## Decision context

`research_context.py` groups observed HTML blocks by headings and ranks sections
against the current question and its required evidence. Unicode tokenization,
identifier/camel-case splitting and a local BM25-style score supply retrieval
order. This is a generic retrieval algorithm; source credibility and claim
truth are assessed separately. Routing remains a model decision.

The default decision allowance is 6,000 characters per observation. Small
main-text observations up to 2,200 characters retain all candidate sections.
Larger observations use the two highest positive-scoring sections and their
immediate neighbors, in source order. Selected candidate blocks remain intact;
an oversized required package produces `needs_context` rather than slicing a
qualification away. A large observation with no term match also requests
refinement. These thresholds are initial bounds, not a proven optimum.

Main-text extraction supplies decision candidates. The original index supplies
stable section identities and records sections omitted or only partly represented
by that extraction. Exact repeated sections collapse only within one observation
and heading scope, never across independently attributed sources. Original code,
table rows, units, headings and access restrictions keep their source identities.
The original HTML index also retains otherwise unwrapped aside/footer text;
comments, scripts and hidden/template content are excluded.

An `open` action may request `group_ids` with the observed SHA-256. Explicit
section reads use the original index, including text removed by main-text
extraction; unknown IDs and stale observations are rejected. Cached observations
are selected again without a new HTTP request. Literal `focus` reads remain
available for refinement. Each selection has a retained full catalog/artifact;
inline navigation is limited to 24 catalog entries and reports truncation and
the omitted count. Catalog pagination is not implemented: a literal focus is
the current route to sections outside that inline catalog.

`policy_view` passes passages, concise source/access state, observed titles,
selection coverage, claim references and compact action history to the policy.
Raw request bodies, artifact internals and duplicated assessment quotations stay
in the evidence journal. Newly reviewed supplemental passages enter subsequent
decision context only when cited by a claim.

## Independent review

`review_view` loads and hash-checks the retained original block artifact for each
read source. The reviewer selects original sections independently of the
planner's excerpts. Small observations retain distant qualifications without
query-term overlap when their full sections fit; long pages use scoped retrieval
and explicitly report omitted sections as described below.
Legacy readers without retained originals are labeled `provided_passages_only`.
Missing or corrupt referenced originals stop assessment explicitly.

Successful review registers supplemental passages before exact quotation
validation and emits `research_review_evidence`. A quotation must still occur in
its referenced observed passage. The existing source/claim assessment, origin
grouping and conservative verdict rules remain in effect. An unchanged assessed
candidate is reused at conclusion instead of starting another review.

Review preflight accounts for the full serialized prompt using the runtime's
conservative UTF-8 input allowance and reserves 6,000 output units. If the
remaining allowance cannot accommodate it, assessment stays incomplete with an
explicit diagnostic and retained observations. This guard is not provider token
accounting. The original review view may be larger than the compact decision
view. Oversized required sections remain an explicit incomplete inspection.

## Reproduced offline measurements

Harness: `tools/probe_research_context.py`. Raw results:
[`context-measurements-phase4.json.gz`](../tests/fixtures/research_corpus/context-measurements-phase4.json.gz).
It records expanded input hashes, manifest/source/harness hashes, dependency
versions, selected passages, omissions, annotated distractors and scoped latency.
The human reference annotations are not supplied to the selection algorithm.

Both controls use the same current source-aligned extractor. The control uses
the phase-3 initial 12,000-character window and decision-view serialization;
the candidate uses question selection and compact serialization. These results
isolate that combined component change, not a historical end-to-end run.

| Case | Candidate gold coverage | Selected characters, control → candidate | Evidence JSON bytes, control → candidate |
| --- | --- | --- | --- |
| Long documentation | 3/3 | 2,590 → 1,458 | 9,268 → 6,774 |
| Article | 3/3 | 309 → 309 | 3,643 → 2,739 |
| Table/code | 4/4 | 232 → 232 | 4,206 → 3,005 |
| JavaScript shell | 0/1; rendered read needed | 40 → 40 | 2,131 → 1,389 |
| Copied sources | 3/3 | 415 → 415 | 6,851 → 4,208 |
| Contradiction | 3/3 | 291 → 291 | 4,386 → 2,803 |
| Blocked response | Not applicable; no read evidence | 0 → 0 | 514 → 519 |

The 16 statically accessible reference passages survive both controls, with no
critical omission in those cases. Total selected text falls from 3,877 to 2,745
characters (29.2%); decision evidence JSON falls from 30,999 to 21,437 bytes
(30.8%). JSON measurements exclude the action schema and policy instructions.
The recorded sum of warm per-document selection medians over 25 samples is
below 1 ms on this machine; it excludes extraction, transport and model latency.

The harness performs zero network, browser or model calls and incurs zero
provider cost. Billed token usage is unknown, not inferred from byte reduction.
The static JavaScript case remains incomplete; Chromium behavior is exercised
separately by acquisition tests. The blocked fixture is excluded by its access
adapter, not a successful page read. These seven synthetic cases do not establish
real-web semantic quality or general noise reduction. Additional retained text
outside annotated gold spans is not automatically irrelevant.

Reproduce from the repository with the research extra installed, choosing a
disposable evidence root and an output path:

```sh
BIGBRAIN_EVIDENCE_ROOT=/tmp/research-context-evidence \
  .venv/bin/python tools/probe_research_context.py \
  --output /tmp/context-measurements.json.gz --samples 25
```

## Validation and next gate

Full regression: 1,464 passed, 8 skipped, 9 warnings in 185.87 seconds. Skips
are the optional phase-2 extractor benchmarks requiring Markdownify. After the
last compact-catalog metadata adjustment, the final research suites passed all
106 tests in 3.57 seconds, including real offline Chromium. Reports are retained
in the local working folder as `bigbrain-research-phase4-regression.xml` and
`bigbrain-research-phase4-focused.xml`; unrelated memory and lockfile edits were
preserved.

Eighteen targeted context tests cover whole-block/neighbor selection, original
section refinement, exact-repeat scope, Unicode identifiers, stale identity,
cached reads, distant counterevidence, unwrapped qualifications, comment exclusion,
review budget reservation, prompt minimization and runtime quotation registration.
Scripted providers establish prompt plumbing and verdict validation; they do not
prove that a real model will correctly interpret every qualification.

Lexical retrieval can miss synonyms, multilingual equivalents or a distant
condition. The independent original-index review reduces selection dependence
but remains bounded and fallible; an unavailable or oversized review must remain
explicitly incomplete. No Luna reranker is enabled: its marginal gain, omissions,
cost and latency must be measured before adding another model call.

Phase 5 integration and the next-branch improvement boundaries are tracked in
[`RESEARCH_ATELIER.md`](RESEARCH_ATELIER.md). They include the exact lexical
ranking behavior and its remaining semantic/multilingual/cost limitations.
No broad UI redesign or paid model campaign was introduced in phase 4.
# Passage targeting and conclusion allowance (2026-10-24)

API definition terms (`dt`) remain atomic and their description blocks share
the definition context. Literal API focus inspects the original observation,
prefers a definition over headings and index occurrences, and returns its
description and version notes up to the next section. Whitespace introduced
around dotted identifiers by HTML extraction is accepted without changing the
observed text or citation identities.

Decision and review prompts share provenance and heading metadata through a
`passage_contexts` table. Each passage retains its original citation ID, text,
kind and clipping flag, with a `context_ref` into that table. Stored evidence
and public/UI passage contracts retain their full representation. Native
contract schemas are sent once rather than duplicated in prompt text.

Before each decision, the runtime reserves the current independent review
request (including its native schema and 6,000 output allowance), plus 10,000
conservative bytes for draft claims from the next decision. The policy protects
that reserve during provider admission. When another decision and review no
longer fit, collection closes and only conclusion or clarification is accepted.
Insufficient allowance stops before provider I/O and preserves partial evidence.
Unknown provider usage continues to consume the conservative reservation.

Offline replay of the authorized Codex probe: the recorded Python documentation
now yields five focused blocks / 401 text bytes containing `missing_ok` and
`FileNotFoundError`. Compacting its existing 116 passages reduces the complete
decision view from approximately 39,567 to 14,274 bytes. These are serialized
UTF-8 sizes, not provider token measurements.

The initial complete-page review required 135,375 conservative units. The bounded
inspection below replaces that request; no new paid call was made.

## Bounded independent inspection

The serialized evidence view has a hard 12,000-byte envelope, including source
metadata, claims, citation texts, shared contexts and the inspection ledger.
Native report schema, instructions, 6,000 output allowance and the existing
10,000-unit draft-claim margin remain separately reserved. Bytes and provider
tokens are different measurements.

Each read source contributes an independently ranked original section. Cited
passages retain their citation IDs and their original sections are restored in
full, including conditions and version notes. Original artifacts are checked
against their stored hash before retrieval. Ranking runs per question and claim
against the complete index, without consulting the planner's chosen excerpt
list. Two positive anchors per query and their neighbors supply additional
inspection candidates. Optional candidates are admitted round-robin across
sources. Small observations up to 8,000 characters offer every section; large
observations do not fill unused space with unrelated material.

Required sections or citation/source metadata that exceed the envelope stop
review before provider I/O and leave the run incomplete. Sections are atomic:
conditions are never clipped to make them fit. Missing/corrupt artifacts and
citations that cannot be restored from an indexed source also stop review.

The retained inspection ledger records each source's observation hash, selected
section IDs, omitted count and coverage mode. It accompanies the assessment in
the evidence journal. Claims include a scope limitation when sections were
omitted. The reviewer is instructed to request missing evidence whenever its
claim needs omitted content and cannot infer page-wide absence or exhaustive
coverage. Lexical retrieval can still miss a distant semantically phrased
qualification; bounded inspection does not claim to eliminate that limitation.

Offline replay re-extracts the saved Python documentation with the corrected
definition boundaries, then supplies a draft claim about `missing_ok`. Its
bounded view measures 11,910 bytes and the reservation is 31,407 conservative
units (including the draft margin), versus 135,375 before bounding. Relevant
`FileNotFoundError` evidence is present. This verifies admission and evidence
assembly only; the user will validate the live conclusion through the UI.

Validation: 125 research tests pass, including distant counterevidence on a long
synthetic source, complete cited conditions, coverage of every read source,
scope persistence and oversized-section rejection before provider calls.

