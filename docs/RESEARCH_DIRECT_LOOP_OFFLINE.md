# Direct-loop offline checkpoint

27 October 2026. Branch: `feat/research-direct-loop`.

## Implemented boundary

The experimental loop uses the existing acquisition runtime and local evidence
policy with an injected inference adapter. It performs bounded acquire, local
select, finish and clarify operations. A forced finish uses a schema containing
only the conclusion. Request parsing, capture identity and exact quotations are
validated before a result is accepted.

The compact context separates immutable observations from the working set sent
to the model. It ranks observed passages locally, fits excerpts inside 12,000
UTF-8 bytes, exposes omissions and permits exact character windows into oversized
code/table passages. Windows retain original text, indentation, capture identity
and explicit partial-view metadata. Local selection adds zero network operations.

Known input/output replaces the respective reservation; unknown usage retains
conservative units. Acquisition capacity stays within the stricter of the direct
and runtime limits. Deadline and call/input/output reserves can force synthesis.
A read timeout closes acquisition while retaining the synthesis opportunity.
Provider timeouts, invalid output/usage, cancellation and progress errors have
explicit terminal states. Invalid responses retain diagnostic artifact references.

Conclusion validation reuses `apply_assessment`: source roles, exact provenance,
shared origins, contrary evidence and question proof standards remain enforced.
Semantic judgments originate in the synthesis model. Independent-review status
is runtime-owned. A required, unfinished review leaves the result partial.

## Evidence

* Final-tree research selection: 474 passed, eight skipped, 1,398 deselected,
  six warnings in 20.25 seconds.
* Seven annotated corpus cases retain required passages and qualifications inside
  the working set: seven passed in 0.75 seconds.
* First complete backend: 1,854 passed, eight skipped, nine warnings in 189.79
  seconds. This precedes the final local-window and cap regressions.
* Final-tree complete backend: 1,871 passed, eight skipped, nine warnings and one
  noisy-dispatch timeout in 210.20 seconds. The failing case is
  `TestReentrantEvents.test_noisy_brain_high_event_throughput`. The full-suite
  validation gate remains open.
* Baseline merge `3829317` passed GitHub CI on Python 3.12, Python 3.13 and
  frontend. The current implementation has local evidence only.

Logs and source hashes are in the adjacent tests workspace at
`research-efficiency-evidence/direct-loop-offline-20261027/`.

## Remaining boundary

The provider and worker defaults still select the preceding engine. Inference
is scripted in the offline journeys. Native generation, retained-context
forecasts, usage capture, durable worker continuation and complete chat/Atelier
delivery remain phase 3 work. No live model call was made for this checkpoint.

The existing extractor and restricted network layer remain in use. Corpus results
establish bounded mechanical coverage for the annotated cases. Source-wide recall
and live semantic selection need the frozen live campaign after integration.
