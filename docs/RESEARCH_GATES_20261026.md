# Research architecture gate audit — 26 October 2026

Implementation base: `85568de00e9eda239792dafc93121f0106aae48d` on
`feat/front-decision-v1`. The current changes remain in the working tree.

## Implemented responsibilities

`research_workflow.py` provides the production worker's finite collection,
freeze, draft, control and settlement journey. It uses the existing acquisition,
batch validation, source limits, quotation anchoring and assessment engine.
The existing action runtime remains available to deterministic callers and
explicitly injected policies/reviewers; default model-backed research uses the
finite workflow.

The front's requesting user turn and resolved research objective are retained.
The fixed question list survives collection. Drafting and control receive the
same `EvidenceDossier` revision. The independent controller checks the original
request, question coverage, source provenance and each assertion. Shared evidence
can support assertions owned by different questions. Existing claim ownership
checks remain enforced.

Passages retain capture, block and range identity in stored observations. Legacy
observations use heading context during restoration. Repeated text in distinct
blocks preserves distinct identities. Frozen packets store exact block anchors,
source links, access failures, section omissions and read text. Required sections
remain atomic. Optional sections are selected within the packet allowance after
measuring anchor metadata. The packet is immutable bytes with a verified SHA-256
digest and a versioned checkpoint.

One targeted complement can create a new dossier revision. The acquisition
decision must stay within the final controller's targets. Every model stage has
a deadline and a single terminal settlement. Input, output, logical calls,
observed usage and unknown usage are recorded separately. Native role histories
are included in forecasts. The production caps are seven logical calls, three
searches, four HTTP acquisitions, two browser upgrades, 120 seconds, 32,000 input
units and 4,000 output units. Output includes reported reasoning usage.

Final control preserves draft qualifications when deriving supported findings.
Original-request gaps prevent complete delivery. A cancelled or failed control
retains an unchecked draft with a partial/cancelled outcome. The Atelier displays
the active stage and distinguishes transport, budget, deadline and schema causes.
Official API reference prices use a dated explicit model mapping; unknown usage
and unpriced cache-write tiers keep the estimate incomplete.

## Live follow-up — 27 October 2026

Gate 4 failed its first live waves. Their transport, packet-size, admission and
control-generation corrections are consolidated in
[RESEARCH_LIVE_BLOCKERS_20261027.md](RESEARCH_LIVE_BLOCKERS_20261027.md).
The offline gate results below retain their source-specific scope. Live readiness
requires a successful campaign on the corrected sources.

## Approved subscription policy

The selected Codex provider retains native conversation history. Its current
`chat_complete` implementation accepts `max_tokens`, while the app-server
`turn/start` packet contains no corresponding output limit. Reported native
usage arrives during or after inference. Automatic compaction has a separate
128,000-token threshold and performs additional inference; it cannot establish
the approved 32,000 aggregate input allowance.

The official [app-server documentation](https://learn.chatgpt.com/docs/app-server)
documents native history compaction and token-usage notifications. The inspected
adapter and documented interface provide insufficient evidence of the required
bounded context/output contract. The user approved the monitored subscription
policy on 26 October 2026. Codex declares `research_budget_policy="monitored"`;
its bounded-context capability remains accurately recorded as unavailable.

Consumed input/output thresholds govern monitored admission. Forecasts and closing
reserves remain visible in the admission ledger. An in-flight native turn
can exceed them. The runtime records measured excess, preserves the exact usage
coverage, settles the attempt and prevents subsequent model calls. Missing usage
consumes its conservative reservation. Seven logical calls, acquisition quotas
and the work deadline retain their explicit bounds. Native cleanup remains
bounded by the existing interruption handling.

Actual Codex adapter tests exercise RPC submission, native cumulative usage,
three stable role threads and four nominal turns. They verify that the collection
thread is reused and that independent control has its own thread. Input overruns
during collection, drafting and control, output overruns, and absent native usage
are covered without account access or inference. Existing tests continue to cover
strict rejection of providers with retained context and no declared budget policy.

Gate 4 remains a separate live authorization. Offline scripted RPC establishes
transport mechanics and policy enforcement. Native quota usage and reasoning
quality will be measured during that frozen campaign.

## Offline evidence

- Exact restoration, dossier tampering, hash stability, transition safety,
  independent role packets, final coverage, seven-call recovery, cancellation,
  malformed responses, per-stage deadlines and overrun settlement have focused
  offline tests.
- The existing seven-family synthetic corpus retains every annotated critical
  passage inside a 6,000-byte dossier. Rendered corpus observations are explicit
  fixtures. Separate worker acceptance uses real Chromium with routed offline
  HTTP resources.
- The production Atelier browser journey replays workflow observations, checks
  active control, conversation isolation, reload and idempotent terminal replay.
- A full backend run during implementation passed 1,732 tests with eight skips
  and nine warnings in 185.18 seconds. Later changes require the final run below.
- Frontend baseline during implementation: 133 tests and production build passed;
  a later diagnostic regression test requires the final run below.

Final offline verification:

- Backend run: 1,746 passed, eight skipped, nine warnings, 190.61 seconds.
- Final packet-isolation and blocked-outcome adjustments passed all 327 research
  tests in 16.40 seconds after that full run. Independent control receives claims
  and citations without the drafter's basis or status fields.
- Frontend: 135 tests passed; TypeScript and production build passed. The existing
  large-bundle warning remains.
- The real Chromium Atelier journey passed, including active control, switching
  conversations, terminal restoration after reload and idempotent event replay.
- The twelve-case campaign JSON parsed successfully; whitespace validation passed.

Logs and final module/corpus/campaign SHA-256 fingerprints are retained under the
adjacent tests workspace in `research-efficiency-evidence/gates-20261026/`.
The backend full-suite log precedes the two final adjustments listed above;
the research-suite log establishes their current results. Local tests
establish deterministic behavior and packet integrity. Model reasoning
reliability remains Gate 4 evidence. GitHub CI has no result for these working-tree
changes. No external model inference was used during this implementation.

## Gate status and next preparation

- Gate 1: integrated contracts and dossier integrity pass their offline audit.
- Gate 2: closed offline under the approved monitored Codex subscription policy.
- Gate 3: closed offline with integrated suites and production browser acceptance.
- Gate 4: the twelve-attempt specification is prepared in
  `RESEARCH_GATE4_CAMPAIGN.json`. Its public-source cases and controlled synthetic
  source cases are distinguished. Live execution requires the recorded source
  fingerprint freeze and separate user authorization.

A valid final control may conclude after an in-flight threshold overrun. Its
measured excess remains in the result, and further model calls are prevented.
Collection overruns stop acquisition; drafting overruns prevent subsequent control.

The research-only reference amount at the token thresholds is $0.0624
for twelve Luna Standard short-context API-equivalent attempts. An in-flight
overrun can exceed this reference amount. Front usage,
Brave service charges and actual subscription consumption require separate
accounting. The price snapshot was checked on 26 October 2026 against the official
[API pricing page](https://developers.openai.com/api/docs/pricing).
