# Direct research loop

Date: 27 October 2026. Branch: `feat/research-direct-loop`.
Baseline: `38293175c03ccece92bab59a5137ebf7ff48b9e8`.

## Current decision boundary

The direct loop is active, and the latest allocation changes have offline
evidence. Reliable selection remains open. Use
[the release scope and limits](RESEARCH_CLOSURE_20261029.md) for the
present status. Later sections preserve the original plan and dated checkpoints.
The iteration closes with targeted documentary research and explicit partial
outcomes. Complex comparisons remain experimental. Further architecture work
starts with task focus and collaboration decisions.

## Implementation checkpoint — 28 October 2026

Follow-up: [evidence transfer](RESEARCH_EVIDENCE_TRANSFER_20261028.md) now includes
runtime-bound citations, a 1,909-pass backend checkpoint and final frontend
SQLite/PostgreSQL outcomes. PostgreSQL full coverage remains open.

The production model-driven documentary worker now selects the direct loop.
Authenticated delivery, continuation and terminal Atelier presentation have real
frontend evidence. Git and Python completed; PostgreSQL still has coverage gaps.
Source expiry, native usage ordering and premature partial synthesis corrections
are documented with their measured limits in
[the frontend cutover report](RESEARCH_FRONTEND_CUTOVER_20261028.md).
The deployment and future-tense descriptions below preserve the original design
decision; this checkpoint records its current implementation boundary.

## Decision and evidence

The user selected a reduced architecture with acquisition and orchestration owned
by BigBrain. The preceding multi-role workflow is preserved in the baseline.
Its live acceptance remains open. The replacement will enter production after
its own offline and live acceptance gates.

The last wave exposed three distinct problems:

* Selected MDN content could exceed the 48,000-byte frozen dossier.
* Repeated model context and a separate control step could exhaust the monitored
  input and output thresholds before producing a conclusion.
* The blocked-report fixture supplied a retrievable document to the adapter while
  omitting its identity from the actual model request. That path never exercised
  the intended 403 response.

The full backend checkpoint has 1,781 passes, eight skips and one noisy-dispatch
timeout. The dispatch module passes in isolation. Frontend tests and build pass;
the production-component Chromium replay passes. Live chat acceptance remains open.

## Product contract

The researcher answers a scoped question through a short observation/action loop.
It discovers or opens sources, requests relevant sections and produces a concise
answer with exact citations, limits and remaining questions. Ordinary documentary
requests use one research model lane. A source receipt remains immutable and
available outside model context.

The local runtime owns network access, extraction, resource limits, checkpoints,
progress events, cancellation and citation validation. The model chooses relevant
actions and interprets evidence. Website instructions remain untrusted page data.
Generated output never acts directly as a browser or shell command.

Managed research and scraping APIs are outside this redesign. Existing Brave
discovery remains a configurable adapter; supplied public URLs can be read
directly. Brave access and model inference retain their respective external costs.
This phase introduces no additional paid acquisition service. A self-hosted search
index is a separate possible adapter with its own coverage and maintenance cost.

## Closed design decisions

| Concern | Selected behavior | Consequence |
| --- | --- | --- |
| Default orchestration | One model lane with acquire/read/finish decisions | Removes routine draft-to-control dossier duplication |
| Evidence storage | Immutable captures, stable source/passage IDs and source hashes | Full observations stay available for audit and targeted rereads |
| Model context | Bounded working set of passages plus a compact source/coverage ledger | Older text can leave the prompt while its evidence receipt remains |
| Content selection | Local main-content extraction and structural section candidates; the model selects relevant candidates | Source-specific keyword rules stay outside the controller |
| Citation guarantee | Exact quote, capture identity and observed passage checks | Mechanical validity establishes traceability; semantic entailment remains a model judgment |
| Source quality | Claim-specific provenance, version and suitability, with evidence | Official documentation supports API contracts; independent measurements require a different basis |
| Independence | Copies share an origin; unresolved provenance remains explicit | Repetition cannot increase corroboration automatically |
| Coverage | Each requested aspect has cited findings or an explicit gap | Successful transport alone cannot establish complete research |
| Extra review | Explicit user request, caller-declared sensitive use, or an unresolved material contradiction | Review has a recorded trigger and a separate bounded allowance |
| Contradiction | Preserve disagreement and scope; request review or return partial | A fixed budget can end with useful uncertainty |
| Stop behavior | Completed, partial, blocked, clarification, cancelled or failed | Every admitted request receives a durable terminal state |
| Continuation | Explicit request reuses original objective and stored receipts | A conversational retry cannot become a search for its own text |
| Provider sessions | One stable research lane per owner conversation | Native accumulated context remains visible in accounting |
| Deployment | Experimental path stays opt-in until acceptance passes | Existing production behavior changes at a documented cutover |

Extra review uses the relevant claim, conflicting passages and their scope. Its
result remains a separate semantic assessment. A mechanically valid citation
never receives an independent-review label merely because its quote matches.
If review is required and cannot finish, the affected conclusion stays partial.

## Acquisition and compact context

1. Fetch a public URL through the existing restricted acquisition layer. Preserve
   redirects, HTTP status, capture hash, retrieval time and access failures.
2. Identify the main article/reference content and structural blocks using generic
   HTML landmarks. Navigation, promotional sidebars and repeated chrome remain
   outside the default selection. Code, tables, headings and qualification blocks
   retain their structural relationships.
3. Build a local section catalog. Relevance ranking proposes candidates; selecting
   a candidate constitutes a read only after the runtime returns its actual text.
   Ranking establishes relevance candidates, rather than factual truth.
4. Return a compact observation containing selected passages, their headings and
   explicit omitted ranges. Requesting a missing section is a targeted read.
5. Keep every capture and observed passage locally. The working set may evict
   older passage text; a cited passage must be available in the final validation
   set with its original receipt and exact quote.

Long pages never force an entire page or arbitrary large reference section into
every subsequent prompt. Oversized code/table/qualification groups return a
bounded selection diagnostic and navigable child ranges. They cannot silently
become a page-wide assertion. No server-derived rewrite replaces original text.

## Decision and result boundary

Migration ownership:

| Existing module | Role in the replacement |
| --- | --- |
| `research_acquisition.py` | Retain restricted fetching, rendering and capture receipts |
| `research_extraction.py` | Extend generic main-content and structural selection |
| `research_quotes.py` | Retain deterministic quotation-to-observation anchoring |
| `research_sessions.py` | Retain owner-scoped checkpoints and explicit continuation |
| `research.py` | Reuse observed source/passage/action types and progress boundary |
| `research_workflow.py`, `research_stages.py`, `research_complement.py` | Superseded orchestration at production cutover |
| `research_dossier.py` | Preserve historical checkpoints; remove mandatory default dossier assembly |
| `research_assessment.py` | Reuse validation and the optional independent-review adapter |
| `research_delivery.py`, `ResearchPanel.tsx` | Integrate truthful direct-loop delivery and review labels |

A decision selects bounded acquisition actions, a clarification, or a final
answer. Final claims carry passage references, exact quotes, provenance/version
scope, semantic support judgment and limitations. Each fixed question references
its claims and remaining gaps. The runtime checks schema, references, quote spans,
capture identity and resource policy before publishing a result.

The public result separates:

* Answer completeness for the original request.
* Citation integrity, checked mechanically.
* Source suitability and semantic support, judged by the model.
* Independent review status and its trigger, when applicable.
* Access failures, omissions and contradictions.

This boundary reuses the existing acquisition, quotation and delivery contracts
where their guarantees agree. It will replace the staged controller at cutover.
The multi-role workflow remains historical evidence during migration; maintaining
two default research engines is outside the product contract.

## Resource policy

Initial ceilings retain the last approved values: 120 seconds, seven logical
calls, three searches, four pages, two browser upgrades, 64,000 monitored input
units and 4,000 output units. A compact decision packet has a separate byte limit;
12,000 UTF-8 bytes is the initial offline design target. These values are ceilings,
and the simple-case target is at most two acquisition decisions plus one finish.

Before an acquisition decision, reserve one final synthesis allowance using its
actual schema and maximum compact context. Once the remaining allowance only
supports synthesis, the next decision is finish-only. An in-flight Codex overrun
prevents subsequent calls under the approved monitored policy. Preserved evidence
can still be returned with an explicit incomplete status. The controller cannot
guarantee a hard native-token cap through this transport.

Output reservations include reasoning/output overhead reported by the provider.
Absent native usage uses conservative reservations with an explicit unknown flag.
Byte units, estimated tokens, reported tokens, cached tokens, API reference cost
and subscription consumption remain separate fields. API prices need a dated
official reference for the actual selected model.

## Work phases and exit gates

### 1. Evidence and contract

Freeze the preceding results and define the boundary above. Map existing modules
to retained acquisition/evidence code, replaced orchestration, and optional review.
Repair the evaluation inputs so the report URL is genuinely visible to the model.
Record expected answers and retained qualifications independently of model output.

Exit: one written contract, correctly scoped corpus inputs, and explicit tests for
terminal states, citation integrity and the meaning of semantic support.

### 2. Deterministic controller and context

Implement the compact observation/ledger and acquire/read/finish state machine.
Reuse restricted acquisition and immutable receipts. Add tests for long reference
pages, code/tables, qualification retention, navigation removal, unknown usage,
finish reserve, stale receipts, cancellation and malformed decisions.

Exit: deterministic offline journeys complete; every request settles; packet size
stays bounded; no live model is needed to validate the controller's invariants.

### 3. Worker and Atelier integration

Connect the opt-in direct loop to the authenticated worker and existing session
checkpoints. Atelier shows the actual activity, inspected sources, findings and
gaps. Exercise retries, tab switching, reload and final delivery through the real
server path. Persist one conversation-owned research lane.

Exit: worker integration and full chat/Atelier browser journey pass, including
blocked and cancelled work. Review labels reflect the path actually executed.

### 4. Frozen live acceptance and cutover

Use the existing six subject families and held-out reformulations, including the
MDN failures and explicit blocked-report URLs. Freeze sources, prompts, limits and
source revision before the campaign. Execute once per case with the authorized
model. Stop on integrity failure or the declared functional-failure threshold.
Preserve every attempt and count prior failures alongside later results.

Exit: all critical answerable obligations are covered, quotes are genuine, copied
origins and contradictions remain qualified, and blocked cases exercise the
intended access boundary. Report measured latency, calls, usage and unknowns.
Only then switch the default and retire the superseded controller.

## Work discipline

The first implementation batch covers the contract and deterministic controller.
Paid/live probes wait for offline gates and scoped authorization. A failed frozen
campaign produces one consolidated diagnosis against its traces. Further changes
receive a revised contract when they alter acceptance, budget or guarantees.

## Implementation checkpoint — 27 October 2026

The contract, corrected blocked-report inputs and deterministic experimental
controller are implemented on `feat/research-direct-loop`. The checkpoint merge
`3829317` passed GitHub CI for Python 3.12, Python 3.13 and frontend.

The experimental core consists of:

* `research_direct_context.py`: immutable capture-bound passage receipts, lexical
  candidate ranking, UTF-8-bounded packets, explicit omissions, literal character
  windows and local archives surviving working-set eviction.
* `research_direct_controller.py`: separate input/output accounting, independently
  known usage dimensions, acquisition ceilings, finish-only admission and terminal
  states. Forecasts include native retained context at the future adapter boundary.
* `research_direct_result.py`: exact receipt/quote checks and local reuse of
  `apply_assessment` for source roles, provenance, copied origins and proof standards.
  Semantic inputs stay attributed to the synthesis model; independent review has
  a separate runtime-owned status.
* `research_direct.py`: finite acquire/select/finish/clarify execution over the
  existing acquisition runtime. It reserves synthesis time, supports local range
  selection without another network read, and preserves terminal diagnostics for
  malformed output, cancelled calls, timeouts and unsupported monetary caps.

Scripted offline adapters exercise the actual acquisition/runtime boundary. A
simple fixture completes with one read and two admitted model calls. These counts
describe scripted mechanics; live reasoning, native usage and cost measurements
remain pending. The seven manually annotated corpus cases retain their required
passages and qualifications within 12,000-byte working sets. Every omitted range
remains explicitly represented by its passage catalog or window metadata.

Provider integration and production cutover remain pending. The modules have no
default worker selector yet; the existing researcher continues to use its previous
workflow. Phase 3 must bind native inference forecasts and usage capture, persist
the direct outcome through the worker, expose the actual review status in delivery,
and exercise the complete chat/Atelier path. Additional semantic review currently
keeps required cases partial until that adapter has genuinely completed.

Source acquisition continues to use the existing extractor and security boundary.
The compact working set bounds selected observations and reports their omissions.
Source-wide extraction recall and native-model selection remain live acceptance
questions. Runtime replacement and default cutover are pending.
Current implementation evidence and remaining integration work are recorded in
[RESEARCH_DIRECT_LOOP_OFFLINE.md](RESEARCH_DIRECT_LOOP_OFFLINE.md).

Two authorized native probes now have evidence in
[RESEARCH_DIRECT_LOOP_LIVE_20261027.md](RESEARCH_DIRECT_LOOP_LIVE_20261027.md).
MDN base completed; SQLite base failed final source-assessment validation after
two missing-focus reads. Provider integration is experimental. Subsequent packet
feedback/navigation and source-assessment corrections passed seven regressions.
The frozen five-probe assessment closes this experimental iteration with three
runtime-complete outcomes, two partial outcomes and zero technical failures:
[RESEARCH_DIRECT_FIVE_PROBES_20261027.md](RESEARCH_DIRECT_FIVE_PROBES_20261027.md).
Manual coverage qualifications and unknown native usage remain explicit.
Default worker/chat/Atelier cutover remains pending.
