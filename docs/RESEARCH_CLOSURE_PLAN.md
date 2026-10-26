# ResearchBrain architecture and closure plan

Date: 26 October 2026. Status: proposed; implementation awaits user approval.

## 1. Outcome and boundaries

Deliver a bounded documentary researcher that answers a concrete question from
read public sources, preserves material qualifications, and terminates with an
accurate coverage statement. It also supplies evidence to other brains through
the same result contract. ResearchBrain and WebAppBrain retain separate roles.

V1 supports factual documentation questions, version comparisons and small
comparisons across public sources. Discovery uses Brave; acquisition uses the
existing guarded HTTP reader and bounded browser upgrade. Open-ended exhaustive
surveys, authenticated browsing, CAPTCHA bypass, autonomous actions on websites,
new scraper dependencies, semantic reranking services and Laya deployment remain
future work. The action/observation records remain usable for later Laya studies.

This document replaces the proposed next implementation sequence for research
closure. Earlier documents retain historical results. Existing unvalidated work
does not become accepted through this plan.

## 2. Observed baseline

- Individual real Git and SQLite journeys completed with cited chat delivery.
  Repetitions exposed incomplete coverage, context loss and protocol failures.
- A previous full backend run passed 1,667 tests, with eight skips. Subsequent
  changes mean that result does not describe the current entire working tree.
- The latest retained focused run passed 107 tests and failed one original-section
  restoration test. Repeated prose can map an excerpt to unrelated sections.
- Documentary completion currently checks reference integrity and declared gaps;
  this provides insufficient independent evidence of question completeness.
- Collection and review assemble different context selections. Native retained
  histories also complicate admission estimates and usage measurement.

Baseline references: `../bigbrain-preview/bigbrain/research.py`,
`research_documentary.py`, `research_context.py`, `research_assessment.py`, and
`research-efficiency-evidence/END_TO_END_20261026.md`. The latter report covers
only part of the retained campaign; the closure report must include later runs.

## 3. Decisions proposed for approval

### A. One fixed request and one evidence dossier

The existing front decision supplies at most six atomic obligations, source and
version constraints, and output language. No additional planning call is added.
The worker checks structure and retains the original request alongside the
decomposition. The final controller checks the original request too, so a front
decomposition omission cannot silently narrow completion.

Collection can propose retrieval actions and evidence associations. The runtime
owns source IDs, capture identities, allowed actions, budgets and state changes.
The model cannot expand obligations during collection. Genuine ambiguity yields
an explicit question; resource exhaustion yields a bounded research result.

One immutable `EvidenceDossier` revision contains:

- Request, obligations, constraints and acquisition limitations.
- Source/final URL, capture time, version evidence and shared-origin information.
- Exact original block IDs, locators, character ranges and capture hashes.
- Selected original text with enclosing qualifications and section boundaries.
- Evidence associations to one or several obligations, and an omissions ledger.
- Access failures, unresolved contradictions and missing evidence.

Excerpt identity uses capture/block/range, rather than substring matching across
the document. Selection never silently truncates a required qualification. A
unit that exceeds capacity produces an explicit selection limitation.

Drafting and control consume the same dossier revision. Control is independent
of the drafter's reasoning and confidence, but remains limited to the supplied
evidence. It cannot certify that omitted page sections contain no counterexample.

Tradeoff: shared evidence avoids inconsistent reconstruction; completeness beyond
the inspected scope remains uncertain. Preserve that scope in every verdict.

### B. Explicit stages and one targeted recovery cycle

`scope -> collect -> freeze -> draft -> control -> settle`

Control may request one targeted complement, with exact missing obligation and
needed evidence. Then: `collect_complement -> freeze_new_revision -> revise ->
control -> settle`. Contradiction findings may use this same allowance.

The runtime permits no second recovery cycle and no return to open-ended
planning. Access problems and malformed proposals consume existing allowances.
Every admitted run settles once, including cancellation, timeout, provider error,
restart interruption and missing usage. Restart restores observations and marks
an interrupted attempt; automatic paid continuation remains disabled.

Tradeoff: difficult questions may end partially answered. This is acceptable when
the remaining gap is real and visible. Excessive partial results on answerable
acceptance cases fail the usefulness gate.

### C. Dedicated final control using Luna

Keep Sol 6.1 low for front delegation and Luna low for research. A separate Luna
control call receives the frozen dossier, draft, obligations and original request.
It receives neither collection conversation history nor the drafter's reasoning.
This gives role separation; same-model errors can remain correlated.

Control returns per-assertion support, qualifications, contradictions, and
per-obligation coverage. Runtime checks IDs, source captures and exact quoted
anchors. A source domain or model confidence cannot establish semantic truth.

Coverage can reference several assertions and evidence units. Existing strict
claim/question ownership stays in force during this work: cross-question facts
are represented through shared evidence associations and separately scoped
assertions. No cloning solely to bypass a rejected review report is permitted.
Any future many-to-many claim ownership change requires its own approved contract.

Tradeoff: one extra call on simple questions purchases a consistent delivery
gate. No automatic Sol escalation or provider fallback is introduced.

### D. Source suitability is claim-specific

Record three separate judgments: source provenance, relevance/support for the
claim, and independent corroboration when required. Official product manuals
usually support their own documented behavior; empirical/general claims may
require different evidence. Blogs and forum posts can support attributed
experience. Copies and common-origin reports form one origin group.

For each question, use direct documentary support or an explicitly required
corroboration standard. Freshness follows the question and source version.
No automatic year suffix, domain truth score or universal two-source quota.
Conflicting evidence stays visible. High-stakes guidance beyond a documentary
explanation may require a stricter standard and an incomplete outcome in V1.

### E. Finite calls and bounded context

Proposed initial defaults, frozen before implementation acceptance:

| Resource | Limit |
| --- | --- |
| Initial collection model decisions | 2, grouped actions supported |
| Draft and final control | 1 call each |
| Targeted recovery | 1 collection call, 1 revision, 1 control |
| Total research logical model calls | 7 maximum; nominal path 4 |
| Search acquisitions | 3 total |
| Page acquisitions | 4 total, at most 2 browser upgrades |
| Research deadline | 120 seconds, excluding front delegation |
| Aggregate input allowance | 32,000 tokens or conservative units |
| Aggregate output allowance | 4,000 tokens or reserved output units |

All retries, malformed output and recovery count toward these totals. No hidden
model selector, reranker, summarizer or repair call is added. Native requests/tool
attempts are recorded separately from logical calls and have explicit bounds.
Stage deadlines must reserve final control and settlement before collection starts.
Recovery is available only when its complete closing envelope fits.

The dossier is assembled to fit the remaining input allocation and final-control
allowance. Original artifacts remain stored outside model context. Collection
receives compact current state and newly selected evidence; full dossiers and
instructions must not be repeatedly appended to an unbounded native history.

Retain one user-facing research identity. Use fixed role-scoped inference lanes
and provider-supported bounded context where available. An existing conversation
binding alone does not prove context compaction. Before live acceptance, inspect
actual request/history behavior. If bounded context cannot be demonstrated with
the selected Codex transport, report a transport blocker and obtain approval for
an alternative; do not silently reset sessions, change providers or exceed caps.

Tradeoff: these are conservative starting caps, not established performance
claims. Offline packet sizing must show the nominal and recovery envelopes fit.
An infeasible envelope is surfaced before live execution; limits require explicit
approval to change after the acceptance campaign is frozen.

### F. Official API pricing as the reference cost

Use exact public API model IDs and official provider prices as a dated reference.
Record currency, pricing URL, verification date, input/output/cache categories,
and any distinct reasoning or tool charges. Internal aliases require an explicit
mapping; no guessed alias-to-price mapping is allowed.

Reference cost = uncached input x official input rate + cached input x official
cached rate + billable output x official output rate + applicable official fees.
Use the provider's documented accounting to avoid double-counting reasoning.
Aggregate calls by phase and entire journey, including rejected/failed calls.

For subscription execution this is an API-equivalent estimate, separate from
subscription quota consumption and actual invoicing. Unknown usage remains
unknown. Show measured reference subtotal, measurement coverage and separately
labelled conservative admission estimates. Serialized bytes and reservations
must never be presented as measured tokens. Unknown cache usage cannot receive a
cache discount. Missing model pricing yields an explicit unavailable estimate.

Verify official prices before the live campaign and freeze that pricing snapshot.
No numeric rates are asserted by this planning document. Search/render service
costs are separate from model-token reference costs. A provisional maximum API
reference envelope follows from the approved token limits and exact model prices;
present it before requesting live-run authorization.

### G. Delivery states and useful partial answers

Use separate outcome fields: execution outcome, answer coverage, and evidence
assessment. Normal incomplete research is displayed as partial, rather than a
generic worker crash. Transport/contract errors retain their actual error class.

- Complete: every requested obligation has sufficient inspected support or an
  explicitly established contradiction answering that obligation; qualifications
  survive delivery and the final control passed.
- Partial: useful supported findings plus exact unanswered obligations/limits.
- Blocked: no adequate answer, with access/environment/protocol reason.
- Cancelled/interrupted: retained evidence and explicit terminal state.

When final control cannot run, retain a clearly labelled unchecked draft or
observations. They cannot receive completed/validated status. The deterministic
renderer preserves verified references and control findings without an extra
front summarization call. Wording must distinguish bounded review from truth
certification and exhaustive search.

Atelier shows active stage, current work, findings, sources and limitations using
existing components. One run/research identity links chat, Atelier and checkpoint.
No independent UI redesign belongs to this plan.

## 4. Implementation sequence and exit gates

### Gate 0: approve the decisions above

Approval accepts V1 scope, same-model separate control, one recovery cycle,
resource caps, API-equivalent costing, bounded-history requirement and acceptance
thresholds below. No live execution is authorized by plan approval alone.

### Gate 1: contracts and offline dossier integrity

Add versioned request/dossier/control/result contracts and transition table.
Map current modules to these responsibilities; adapt existing code in place.
Preserve existing security, source anchoring, cancellation and ownership checks.
Fix exact block/range restoration as part of dossier construction. Remove
superseded runtime branches only after replacement parity is demonstrated.

Exit: scripted tests cover repeated identical prose in distinct blocks, clipped
qualifiers, capture changes, version mismatch, multi-question evidence reuse,
source-origin duplication, omissions and dossier hash stability. Draft/control
must consume the identical revision. No model calls.

### Gate 2: stage controller and resource accounting

Implement finite transitions, closing reservations, terminal uniqueness and the
single complement cycle. Test retained-history accounting and role isolation
through provider fixtures. Add dated pricing mapping and measured/unknown usage
aggregation. No broad provider rewrite or refactor of unrelated brains.

Exit: end-to-end scripted journeys cover nominal delivery, targeted recovery,
contradiction, missing evidence, invalid JSON, deadlines at every stage, cancel,
late result, disconnect/reload and restart. All attempts obey caps and settle.
No model calls.

### Gate 3: integrated offline acceptance

Reuse the frozen source corpus and real offline browser transport. Audit each
case's expected claims and critical reservations before changing implementation.
Run focused suites, full backend suite, frontend tests/build and one browser
journey matrix. Preserve skips and pre-existing failures explicitly.

Exit: current-tree results, exact revision, retained logs, semantic gold criteria
and provider envelope feasibility are ready. Fixes stay within Gates 1-2 scope.
An architectural mismatch stops the work for one consolidated decision.

### Gate 4: one authorized frozen live campaign

Six families: versioned API, database concurrency, calibration/configuration,
JavaScript reference, copied/conflicting sources, and blocked access. Each has
one base question and one held-out reformulation: 12 attempts total, no automatic
reruns. Predeclare complete versus legitimately partial expected outcomes.
At least two journeys include actual chat/Atelier/reload; remaining journeys may
use the authenticated worker boundary to reduce unrelated overhead.

Proposed acceptance: zero critical invented citations, lost safety qualifiers,
false completion or unbounded executions. Every case must settle correctly.
At least 90% of predeclared answerable obligations must be answered with valid
support; all declared critical obligations must be covered in answerable cases.
Blocked/contradiction cases must retain their expected limits rather than inflate
the completion score. Publish case-level results, latency, calls, usage coverage
and API-reference costs. Small-sample acceptance establishes V1 readiness within
this corpus; broader reliability remains an explicit limit.

Stop the campaign on any critical integrity failure or two distinct functional
case failures. Do not patch between campaign cases. Diagnose all retained failures
together. Allow at most one consolidated correction batch and one explicitly
authorized rerun of the frozen campaign. Continued failure triggers a product
decision to narrow, defer or change the blocked layer.

### Gate 5: closure

Publish one concise closure report and reconcile active docs/roadmap, retaining
historical evidence links. Record supported scope, known limits, costs and the
next deferred milestone. Commit/push follows user instructions. Merge requires
explicit user approval and accurate reporting of CI on the exact commit.

## 5. Work discipline and stop conditions

- Implement Gates 1-3 as one agreed scope, with short evidence-based updates.
- Bring new material tradeoffs together before coding them; avoid incident-led
  additions to prompts or new layers outside this design.
- Use existing tests and evidence; no new exploratory live probes during coding.
- Keep paid/quota use behind explicit campaign approval and stated maximums.
- A transport blocker, infeasible budget, changed semantic acceptance requirement
  or need for a new dependency pauses the affected implementation for a decision.
- Do not claim a calendar guarantee. The bounded deliverable is this sequence,
  one frozen campaign and at most one consolidated correction batch. Further work
  requires an explicit decision, rather than an indefinite continuation.

## 6. Approval checklist

1. V1 scope and source-specific evidentiary standards.
2. One shared frozen dossier, separate Luna drafting/control, strict ownership.
3. One targeted recovery cycle and proposed call/time/token caps.
4. Official API-equivalent pricing, with unknown usage retained visibly.
5. Twelve-attempt live campaign, thresholds and stop/correction policy.

All five have recommendations above. Approval can accept them together or amend
specific items before implementation begins.
