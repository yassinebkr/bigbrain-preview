# Research evidence transfer — 28 October 2026

## Scope

Preserve acquired evidence across partial syntheses and continuations, retain
the current limits, and validate the real frontend path. Source selection and
entailment remain model judgments. Literal quotation checks establish provenance
and traceability.

## Exact PostgreSQL replay

The frozen input is the v12 checkpoint for research
`7edba1bd-2e48-4b80-aa0f-9268dfcc6129`, attempt
`dc89102a-1142-445d-aea1-9bfd4c0cf788`. Its copied checkpoint remains unchanged.

The previous packet measured 11,997 bytes and exposed four passages. Its source
ledger, prior summaries and navigation consumed most of the 12,000-byte ceiling.
Only three of the nine cited passage IDs were directly exposed. Three additional
quotation texts were available through identical consultation aliases: six of
nine quote texts were visible. The other cited text and the explicit TRUNCATE
row-rollback qualification were outside the packet, while present in the archive.

The revised packet measures 11,846 bytes and exposes seven passages. All nine
prior quotation texts are visible against their original source/capture,
including aliases. The adjacent explicit row-rollback paragraph is also visible.
Source-specific query rules and larger envelopes are absent from this correction.

## Implementation

* Prior quotes receive continuity priority after receipt identity, capture hash
  and literal-offset checks. Bounded windows keep original offsets and clipping
  metadata. Immediate paragraphs in the same source/heading context preserve
  nearby qualifications. Explicit inspection windows retain priority.
* Auxiliary navigation is proportional to the remaining space. Prior summaries
  are capped at 240 characters each; unobserved source entries carry compact
  identity/status fields. Omitted evidence remains in the archive/catalog.
* Final native synthesis receives the current bounded passage snapshot again.
  Intermediate decisions retain incremental observations. Final forecasts include
  the replayed text, and the same model conversation remains in use.
* URL visits forward the source-language reading intent, mode and refresh flag
  to the reader. An offline regression exercises the actual visit/open boundary.
* Read identity includes the reading intent. A captured live proposal requested
  one section for two different questions; the previous key rejected the second
  request as a duplicate. Exact repeats remain blocked. A controlled proposal
  refusal becomes an error observation before any batch acquisition executes,
  allowing bounded recovery. Batch-level failures remain visible in feedback.
* Explicit unresolved judgments remain unverified after deterministic citation
  checks. Synthesis instructions require claims whose central assertion agrees
  with their limitations. Entailment still requires semantic assessment.
* Native citation proposals select an exposed passage and optional original
  character offsets. The runtime extracts the exact visible span and supplies
  its receipt identity. Both validation layers retain the literal offsets.
  A complete visible window is the default up to 2,000 characters; longer windows
  require explicit selection. Out-of-window spans and stale handles fail closed.
  This removes free-text quotation copying from the native generation contract.

## Verification

The first full suite after continuity changes passed 1,898 tests with eight
skips. The snapshot/visit-intent full suite then passed 1,900 tests with eight
skips. The controlled-refusal and retrieval-identity checkpoint passed 62 focused
tests. The final full suite passed 1,904 tests with eight skips and nine warnings
in 196.79 seconds. The native citation-binding checkpoint passed 61 focused tests.
UI source remains unchanged in this follow-up; its preceding 137-test/build
checkpoint retains its original scope.

The first live continuation after continuity prioritization remained partial.
It used two calls and 116,291 reported tokens, including accumulated native
conversation history. That attempt predates the full final-snapshot change.
Its partial status remains part of the acceptance record.

A fresh original PostgreSQL request then stopped after two calls because its
batch proposed the same section for distinct reading intents. The archived
candidate identifies this refusal exactly. The retrieval-identity and feedback
corrections above were reproduced offline before another frontend continuation.

That continuation exposed a separate quotation-copying failure: its DROP TABLE
quote inserted an ellipsis between two observed sentences. The literal matcher
correctly rejected the fabricated contiguous span. Native runtime-bound citation
assembly addresses this boundary. The quotation and its rejection remain
archived. The strict internal validator still rejects altered text.

## Final frontend results

| Case | Runtime outcome | Model calls | Reported tokens | Observed result |
| --- | --- | --- | --- | --- |
| Original PostgreSQL comparison, fresh conversation | Partial | 5 | 91,377 | Four findings, five literal anchors, four source judgments; requested effects and transactional/sequence details remain incomplete |
| SQLite WAL concurrency and network-filesystem limits, supplied official URL | Complete | 3 | 34,193 | Three findings, six literal anchors, one source judgment; all three requested aspects covered in 11 seconds |

Both final cases settled with no technical diagnostic. PostgreSQL retains its
incomplete status and gaps. SQLite preserves the SQLITE_BUSY qualification,
reader end marks, single-writer restriction and shared-memory/network-filesystem
explanation. Manual inspection compared each SQLite conclusion against its exact
stored quotations. The literal audit checked all eleven anchors across the two
final cases and their capture hashes.

The final PostgreSQL research identity is
`098b3333-8b9a-42fb-8169-a3551e112cab`; SQLite uses
`d7c414b4-7fb9-4d71-9068-af615be84673`. Each native research conversation retains
its own history. Usage totals include native input context across calls; billed
subscription cost remains unavailable.

Full PostgreSQL acceptance stays open. Narrow source selections sometimes expose
a command heading rather than its description, and multi-question evidence
coverage remains incomplete. Runtime-bound citation assembly preserves these
coverage gaps. The successful SQLite case establishes this bounded documentary
journey; broader web reliability requires further evidence. This checkpoint
includes no merge.

## Document-heading and provider-state follow-up

The captured DELETE title selection reproduced a second extraction boundary:
`window(..., focus="DELETE")` returned the command heading and short legend,
ending before its sibling Description section. The reader now supplies the
observed document title. When it confirms the first source heading, a bounded
page-body window includes subsequent sibling sections. Secondary entries retain
their original section boundaries and the 12,000-character limit still applies.
Captured and generic boundary regressions passed; this checkpoint reached 1,906
backend passes with eight skips.

The subsequent live attempt reached final synthesis and raised a TypeError in
prevalidation of model JSON. Its raw final reply was unavailable, so the exact
nullable field in that attempt remains unknown. Inactive null fields are now
canonicalized, while required arrays retain schema validation. Raw wire candidates
are archived before binding; terminal diagnostics link the latest raw candidate.

A provider-bound regression revealed a further state-loss defect: common usage
accounting replaced the whole usage dictionary after each inference. This erased
the direct evidence result, prior wire-candidate references and the single-
complement marker. Standalone adapter replays had bypassed that accounting path.
Usage refresh now updates its own counters while retaining workflow-owned state.
The regression traverses actual `ResearchRuntime.invoke` calls and verifies four
wire candidates, retained prior findings/gaps and one complement across four
provider calls. The research/extraction suite passed 510 tests with eight skips.
The full provider-state checkpoint passed 1,909 tests with eight skips. Its live
continuation then submitted an acquisition proposal during finish-only admission.
The raw wire artifact preserves the exact wrong-phase proposal; validation
executed none of its requested reads. Final synthesis now receives a dedicated
closing instruction set alongside its finish schema and current evidence
snapshot. Ordinary acquisition directives remain confined to the decision phase.
The research/extraction gate passed 510 tests with eight skips after this change.
The final full suite passed 1,909 tests with eight skips and nine warnings in
196.15 seconds.

The last frontend PostgreSQL probe used research identity
`1a871d7d-3775-4a84-a9c5-c4c290bd86a9`. It settled partial in 43 seconds, with
five model calls, four HTTP acquisitions, six findings and five retained raw wire
candidates. All usage dimensions were reported: 98,654 input tokens and 2,808
output tokens (101,462 total). There was no technical diagnostic or threshold
overrun. Twelve literal anchors and four source judgments passed mechanical
auditing. The explicit TRUNCATE data-rollback and RESTART IDENTITY transaction
passages are now cited, with the currval qualification retained.

Manual semantic acceptance remains open. The DELETE finding adds a filter clause
whose selected DROP TABLE quotation establishes row/table preservation alone.
The sequence finding states the CONTINUE IDENTITY default while its chosen
quotations cover RESTART IDENTITY transaction behavior. The claims are broader
than those citations. DELETE/DROP rollback and their sequence effects also retain
explicit gaps. These issues are recorded separately from the repaired capture,
provider-state and final-phase contracts. The earlier SQLite success predates
this last follow-up and keeps its own source-tree boundary.

Evidence directory:
`/home/kwestog/Documents/code/tests/research-efficiency-evidence/evidence-transfer-20261028/`.
The offline replay includes the checkpoint SHA-256, packet sizes, visible texts
and quotation-to-visible-handle mapping. The frontend probes use the existing
Sol front/Luna research role configuration and unchanged admission limits.
