# Extraction comparison — phase 2

Completed 24 October 2026, on `feat/research-evidence`, working tree based on
`3f458b387e50a13436e7cddeb1d9d9d6900e7049`. This is the **acquisition/context
sub-plan**, distinct from the earlier ResearchBrain runtime phase numbering.
Corpus `2026-10-24.1` and its annotations are unchanged.

## Decision

Carry **Trafilatura recall + structured XML + alignment to the original HTML**
forward as the preferred static-extraction candidate for phase 3. Preserve raw
observations and an explicit path back to original structure when extraction
loses material. This is a provisional choice for a bounded prototype, not a claim
of real-web acceptance or an automatic production dependency change.

Markdownify is useful for faithful structural conversion, but on these inputs
retains navigation/advertising clutter. The current reader remains a useful
unfiltered control. Neither is a demonstrated semantic selector.

## Experiment and measured results

Six configurations were actually executed: current `TextExtractor`, Trafilatura
default/recall/precision using XML, Markdownify, and the source-aligned recall
prototype. Every adapter received HTML + URL only, without the question, gold
passages, origin labels or reservations. No content-specific keywords were used.
Every configuration saw the same documents, with both full extraction and the
same initial 12,000-character serialized window. Browser-rendered snapshots were
replayed separately and marked as such.

| Candidate | Static gold retained, bounded / full | Distractor hits, bounded | Selected characters, bounded | Local extraction ms |
| --- | --- | --- | --- | --- |
| Current reader | 11/16 / 14/16 | 6 | 13,449 | 1.23 |
| Trafilatura default | 13/16 / 16/16 | 1 | 13,149 | 34.51 |
| Trafilatura recall | 16/16 / 16/16 | 2 | 3,881 | 17.54 |
| Trafilatura precision | 13/16 / 16/16 | 1 | 13,149 | 35.26 |
| Markdownify | 13/16 / 16/16 | 6 | 13,295 | 15.72 |
| Recall + source alignment | 16/16 / 16/16 | 2 | 3,877 | 30.18 |

Denominator 16 excludes the single passage unavailable in static JavaScript
HTML. The raw JSON uses 17 and lists that missing passage explicitly. Distractor
counts and character totals include the JavaScript shell; blocked content is
excluded by the fixture access-status gate, identically for all candidates.
Timing is the sum of warm medians for individual documents, 25 samples each;
it excludes imports, fixture loading, scoring, network, model and browser startup.
This differs from the phase-1 baseline timing, which included fixture loading.
Model calls, input/output/cache tokens and provider cost are all zero. Character
reduction is **not** a measured token saving or an end-to-end latency gain.

The compressed artifact `comparison-phase2.json.gz` retains full extracted blocks,
URLs, raw/rendered view IDs, observation hashes, versions, source/configuration
hashes, limitations, per-document medians/p95 and all per-case scores. Results
were inspected against the actual extracted text, including code, units, version
scope, study funding, copied attribution links and both sides of the contradiction.

## Concrete limitations and adapter controls

1. Trafilatura emits a caption as a row padded with empty cells. Its unadapted
   XML therefore triggers an ungrounded-passage flag even though no numeric
   value was invented. The prototype restores a caption only after exact matching
   to an original HTML `caption`; genuine data rows require original row matches.
2. An additional case with an actual empty data cell exposes an omitted row.
   The prototype reports original rows missing from a partially extracted table.
   It does not invent zeroes, silently declare completion or claim recovery.
   Full fallback/retention behavior belongs to the next runtime integration.
3. Preformatted text is matched back to the original `pre`, retaining actual
   indentation, argument spelling and punctuation. Unsupported extracted blocks
   are withheld with a limitation. Source locations distinguish normalized
   visible-text offsets from raw HTML byte offsets; mappings are not claims of
   unique occurrences. This does not establish semantic completeness.
4. The recall output loses some section headings in the long manual. The URL and
   version-specific sentence survive in this corpus, but later integration must
   retain original titles/heading context alongside selected blocks. This corpus
   alone cannot establish version-scope preservation on arbitrary documentation.
5. The long fixture has repeated padding. Recall shrinks that input dramatically;
   this advantage is especially sensitive to this artificial construction. It
   still retains obsolete content and unrelated paragraphs. Question-aware
   selection remains a separate phase and will need new held-out cases.
6. The static JavaScript shell yields none of the required temperature evidence
   with any candidate. Replaying the frozen rendered snapshot gives 1/1, proving
   only the extractor can read supplied rendered HTML. No browser was run here.
7. The 403 body is excluded by a supplied fixture status. No live blocking,
   CAPTCHA handling, anti-bot avoidance, stopping or network behavior was tested.
8. Retained attribution links permit later origin analysis; no source-veracity,
   independent-corroboration or final-claim verdict is inferred from extraction.
   Removing this fixture's injected aside is not general prompt-injection proof.

## Crawlee assessment: acquisition rather than content extraction

The official [adaptive crawler guide](https://crawlee.dev/python/docs/guides/adaptive-playwright-crawler)
describes a browser/HTTP combination, a rendering predictor and selector-triggered
fallback. The [API](https://crawlee.dev/python/api/class/AdaptivePlaywrightCrawler)
also exposes request queues, retry/session controls, limits, statistics and stop.
This makes Crawlee a candidate for acquiring rendered observations; it does not
replace the extractor or ResearchBrain's evidence/source assessment.

Architectural recommendation: keep the existing public-page transport under
ResearchRuntime's control initially, and evaluate a bounded browser adapter in
phase 3. If Crawlee is used, its queueing, retry and rendering decisions must
remain visible and accounted for inside the same budgets/Stop behavior. A new
browser path must preserve target/redirect/subresource restrictions. These are
integration requirements, not measured Crawlee failures. Crawlee was inspected
through its documentation; it was neither installed nor benchmarked here, and
there is no measured Crawlee-versus-Playwright performance conclusion.

The extraction options are documented in the official
[Trafilatura API](https://trafilatura.readthedocs.io/en/latest/corefunctions.html)
and [Python guide](https://trafilatura.readthedocs.io/en/latest/usage-python.html).
The structural-conversion control uses
[python-markdownify](https://github.com/matthewwithanm/python-markdownify).

## Reproduction and verification

Use a disposable Python 3.12 environment. Install `requirements-phase2.lock`;
the benchmark used Trafilatura 2.3.1, Markdownify 1.2.3, BeautifulSoup 4.15.0 and
lxml 6.1.3. BigBrain's application environment/dependency manifest was not changed.

```sh
python -m unittest discover -s tests/fixtures/research_corpus -p 'test_*.py'
python tests/fixtures/research_corpus/compare_extractors.py \
  --reader bigbrain/research.py --samples 25 --output /tmp/comparison.json.gz
```

19 checks passed in the dependency-equipped environment: corpus scoring controls,
equal window accounting, actual critical-passage retention, code/units, hidden
script exclusion, explicit empty-cell omission, attribution links, raw/rendered
separation, original code indentation and renamed-product behavior. Optional
extractor tests skip explicitly when dependencies are absent; a skipped test is
not experimental validation.

Phase 2 is complete as a component comparison. Next: phase 3 controlled
HTTP/browser acquisition, retained raw structure, explicit extraction limitations
and bounded execution. Phase 4 selects question-relevant context; phase 5 connects
the resulting observations to ResearchBrain/Atelier; phase 6 measures real-web
usefulness and cost. This phase does not enable those later behaviors.
