# Research scope and native action generation

## Delegation scope

A fresh research delegation can carry `payload.obligations`: one to six concise
factual questions derived from the user's request. The existing Sol frontbrain
decision produces this list alongside its objective and acknowledgement. The
runtime assigns stable `q1` through `q6` identities and sets `scope_locked`.
The researcher collects evidence for those questions. Plan replacement is refused
before I/O. Citation format and response language remain answer constraints.

Legacy requests without an obligations list retain their single initial question.
Continuation uses its checkpoint's original objective, question IDs and scope;
new delegation metadata cannot replace that retained scope. Empty, repeated and
oversized obligation lists are rejected by the front contract and the worker.

## Native generation variants

`research_generation.py` derives compact JSON Schema variants from the shared
Action contract for the Codex decision bridge. Each tool exposes its executable
arguments. Focused reads and explicit section reads have separate closed shapes;
the same variants are available inside grouped requests. Schema versions and
default metadata are supplied by the local parser. Current source, question and
passage identities constrain the generated references.

The API-provider schema path retains its existing shape. Both generation paths
feed the same Action parser and runtime preflight. Admission forecasts use the
actual constrained generation schema. A proposal still needs valid permissions,
resource capacity, selectors and observed citations before execution.

Every invalid Action proposal receives field diagnostics under the existing
decision/time/token limits. The original response is retained as an immutable
artifact. Two consecutive rejections end the attempt. Documentary conclusions
with context-only citations are rejected during preflight and can be corrected
within that allowance; the supporting-evidence requirement remains enforced.

## Source navigation and evidence

Acquisition retains a bounded question-ranked index of original sections. The
decision view uses compact `[section_id, observed_heading]` pairs with the capture
digest. Up to 48 section labels remain visible, with explicit overflow counts;
acquisition retains up to 96 entries. Labels are bounded to 100 characters in the
decision view. This exposes the complete indexes of the tested SQLite manuals
even when the user's French wording ranks English headings poorly.

Index entries provide navigation. Claims cite passages actually returned by a
read. Source text, original locations, capture hashes and quote validation remain
the evidence reference. Source-language focuses and complete heading packets
guide bounded decision context assembly. CLI option tokens preserve dash and case.

Fresh cache consultations reuse captured observations and consume decision/time
capacity. HTTP/browser acquisition counters track actual acquisition attempts.
An expired or evicted capture cannot silently initiate a new acquisition through
a cache-only consultation. Group preflight and execution both enforce quotas.

## Delivery and validation

Completed documentary findings carry source-linked public messages through the
frontbrain to the chat. Qualifications and citations survive that boundary.
The Atelier retains the detailed observations and read passages. Essential gaps
keep the research partial; model-generated citations cannot grant independent
verification to a documentary synthesis.

The retained browser campaign is described in
`../../tests/research-efficiency-evidence/END_TO_END_20261026.md`. It includes
successful and partial attempts, schema failures, screenshots, page-reload checks
and available usage measurements. Passing runtime tests and successful individual
journeys are separate from general model-led coverage reliability.
