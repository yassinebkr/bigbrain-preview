# Research acquisition and context-selection corpus — phase 1

Phase 2 comparison is recorded in [PHASE2_RESULTS.md](PHASE2_RESULTS.md), with
pinned experimental dependencies, reproducible adapters and compressed raw
evidence. The reference annotations below are unchanged.

Phase 4 question-selection results and limitations are recorded in
[`RESEARCH_CONTEXT.md`](../../../docs/RESEARCH_CONTEXT.md). The compressed
`context-measurements-phase4.json.gz` records actual selected passages, coverage,
source/harness hashes and serialized evidence sizes. Reproduce it with
`tools/probe_research_context.py` from the repository; it uses no network/model.

Version: `2026-10-24.1`. Manually authored on 24 October 2026. All documents,
organizations, URLs and measurements are synthetic. This small development
corpus tests known failure modes; it does not estimate performance on the real
web. No network, credentials, model or paid API is used.

## Reference annotations

`manifest.json` is the human reference, never supplied to the extraction or
selection candidate. Each case specifies the question, accessible observations,
necessary exact passages, critical omissions, reservations and expected outcome.
The HTML files are candidate inputs. `origin` labels are evaluation ground truth:
the copies expose attribution links in HTML so origin can actually be inferred.
A different hostname must not count as independent corroboration.

| Case | Necessary observations and limits |
| --- | --- |
| Long documentation | v3 signature, narrowly suppressed exception, version boundary; obsolete wrapper is a distractor |
| Article | measured result, laboratory-only scope, small sample, funding |
| Table/code | preserve each method/value/unit association and code argument names |
| JavaScript | shell is insufficient; rendered fixture contains the range and use restrictions |
| Copies | original assertion plus attribution of both copies; one originating announcement |
| Contradiction | vendor statement, opposing reproduction, version difference and reproduction scope |
| Blocked | HTTP 403 and access notice; discovery snippet cannot establish the result |

The long document has a deterministic 80-section prefix, defined in
`document_html`, placing the required removal section beyond the runtime's
12,000-character window. Hash the expanded inputs, not just their template.
The rendered JavaScript file is a frozen browser observation; it is not produced
by executing JavaScript and must not be exposed to an HTTP-only candidate.
The 403 case must be passed through a transport/status adapter; its HTML is not
an accessible report. These scenarios do not prove browser or anti-bot support.

## Measurement contract

Run `python evaluate.py` to validate annotations and print expanded input hashes.
Run `python -m unittest discover -s . -p 'test_evaluate.py'` for scoring controls.
Run `python baseline.py /path/to/bigbrain/research.py` for the current extractor.
Run `python evaluate.py --candidate results.json` for a saved candidate.

Candidate JSON maps case IDs to `passages: {document_id: [verbatim_text, ...]}`,
`reservations: [reference_label, ...]`, `status` and `telemetry`. Keep the actual
answer and rationale separately for human review; matching labels alone cannot
prove that a reservation was understood. A passage must retain its document ID.
For a browser observation, record `observed_views: {document_id: "rendered"}`;
otherwise grounding is checked against raw HTML only. Omitted status/reservation
fields remain unassessed (null), rather than being counted as semantic failures.

Report per-case results rather than collapsing them into an arbitrary score:

- Passage recall and explicit critical omissions. Exact matches normalize
  whitespace; table references use ` | ` between cells. Paraphrase-aware semantic
  review is separate, so this metric is deliberately strict about lost structure.
- Annotated relevance fraction: selected characters belonging to gold spans,
  with overlaps counted once. `non_gold_fraction` measures extra context, not
  semantic irrelevance: some unannotated context can be useful. Also report hits
  on manually designated distractors and invalid/ungrounded passages.
- Reservation coverage, outcome and origin independence reviewed against the
  underlying answer and observed evidence. Source status is claim-specific;
  neither official provenance nor popularity implies a true assertion.
- Actual calls, input/output/cache tokens, currency and reported cost. Unknown
  values stay null; estimates must be labeled separately. Offline extractor-only
  runs have zero model calls and zero provider cost, not zero computational cost.
- Latency with an explicit scope. Local extraction timings exclude network,
  browser and model time; later live runs must record end-to-end and phase times.

## Gates for subsequent comparisons

All critical passages must survive selection or the case must explicitly report
the missing evidence and abstain from the unsupported conclusion. For JavaScript,
correct abstention passes the access behavior gate but does not satisfy evidence
completion. For blocked access, recall is undefined, not 100%; assess honest
abstention and absence of fabricated evidence instead.

No fabricated passage, snippet-as-read-evidence, hidden contradiction or invented
independent confirmation is acceptable. Extra context and latency can then be
compared at equivalent evidence coverage. There is no universal noise threshold
yet: establish the baseline before choosing one. The gold candidate is only a
scoring control, never evidence that the real system passed.

Any annotation change increments the corpus version and invalidates old
comparisons. Record candidate revision/configuration, input hashes, metrics and
human review with each experiment. No extractor/model choice is made in phase 1.

## Initial extraction baseline, 24 October 2026

`baseline-current.json` records 25 local samples per case against the actual
`TextExtractor` class extracted from the current source AST. The adapter mirrors
the reader's newline joining and initial 12,000-character window, without focus.
It deliberately does not run a research policy or assess source credibility.

| Case | Gold passage coverage | Observed limitation |
| --- | --- | --- |
| Long documentation | 0/3 | Required section lies outside the initial window |
| Article | 3/3 | Both advertising/navigation distractors retained |
| Table/code | 2/4 | Explicit row associations absent; code and warning retained |
| JavaScript | 0/1 | Shell only; browser acquisition still needed |
| Copies | 3/3 | Attribution text retained; independence judgment untested |
| Contradiction | 3/3 | Both sides retained, along with injected instruction |
| Blocked | Not applicable | Adapter excludes 403; abstention behavior untested |

Table coverage is a strict structural annotation result: it does not prove that
a model could not reconstruct rows from the flattened text. Reservation/status
fields in this extractor-only baseline are unassessed, not semantic failures.
Local median timings are below 2 ms per case in this run; they say nothing about
real request latency. Paid model calls and provider cost are zero.
