# Drawing 42 qualification baseline

The two retained Terra traces supply a starting point for the CAD performance
work. Both runs included operator intervention. Their phase totals describe
observed inference time and exclude gaps between calls.

| Metric | Terra low | Terra medium |
| --- | ---: | ---: |
| Construction calls | 48 | 51 |
| Inspection calls | 1 | 1 |
| Construction inference (s) | 1,310.49 | 1,264.77 |
| Inspection inference (s) | 114.07 | 95.20 |
| Reported input tokens | 6,336,216 | 6,417,341 |
| Cached input tokens included above | 1,702,784 | 2,337,280 |
| Reported output tokens | 35,063 | 33,842 |
| Calls with unknown usage | 1 | 1 |
| Accepted construction steps | 22 | 29 |
| Native construction failures | 4 | 2 |
| Published checks | 69 | 94 |

The published solids have effectively identical measured volume. Their retained
bounds differ along Z, so a regression comparison must check the local geometry
and agreed coordinate frame before treating the exports as interchangeable.
The two runs also used different implementation snapshots.

## Reproduce the totals

Read the retained `low-full-usage.json` and `medium-full-usage.json` files in the
local Terra qualification evidence directory. For each metric, sum the
construction and inspection phase fields. Obtain accepted steps, native failures
and published check counts from `final-artifact-audit.json`, keyed by the same
document IDs. Keep cached tokens inside the input total and count unknown usage
calls separately.

## Benchmark requirements

Capture receipt, acknowledgement, delegation, first model content, first accepted
geometry and verified delivery under one run identity. Measure native work,
inspection and presentation separately. Provider queue time, elapsed time
between interrupted attempts and browser presentation time remain unknown in
the retained totals. Report any API-price-equivalent estimate separately from
subscription usage. Include failed attempts in prospective cost per delivery.

Replay the original contract and checkpoint chain on a disposable copy before
running new inference. Compare local dimensions, continuity, cut safety and
revision lineage. Proposed thresholds from the roadmap remain subject to review
before live comparison.
