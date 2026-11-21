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

## Native checkpoint recovery

On Linux, a disposable copy of the Terra medium document recovered all 29
accepted checkpoints in order through `CadExecutionStore.recover`. The replay
used SolidCraft 0.28.0 with executable SHA-256
`866a8ded1f66e0fbd6f01d6046502b2a62e98da6403c127edfdbce8a8e7a549e`.
The stock installation has a different executable digest. Each recovery
verified the native file hash and compared the reopened design inventory
against its retained observation under the original contract digest.
Observed recovery times ranged from under 0.01 seconds to 1.98 seconds.
This measures checkpoint reopening and identity verification. Command
reconstruction from an empty document and fresh metrology remain separate
qualification steps.

## Reconstruction from the command journal

Run `python -m tools.replay_cad_checkpoints DOCUMENT --engine CLI` from the
repository root with the retained document directory and its qualified CLI.
The tool verifies proposal hashes and original parent links before remapping
parents to the new temporary chain. The native cut guards run on every group.

All 29 groups executed on Linux. Design inventories, parameter graphs and
remaining obligations matched at each group. Cut reports matched in measured
values and verdicts. Four groups, 18, 21, 24 and 27, produced different
`before_native_sha256` and `cutter_sha256` values. The tool reports strict
evidence divergence with a nonzero exit status. The cause of the byte-level
differences and the final independent metrology remain unqualified.

### Independent STEP comparison

The reconstructed export and the revision 5 STEP returned identical
`inspect_step` results, including analytic bounds and the measured volume
of 28,094,977.13234817 mm³. Reproduce this comparison with
`--reference-step DOCUMENT/revision-5/part.step`. The strict cut-evidence
comparison still flags the four snapshot and cutter file hashes. Fresh
local section probes are outside this particular STEP comparison.

## Decision packet cost

The 51 retained construction packets grew from 39,324 to 170,727 UTF-8 bytes.
Across the corpus, observations account for 1,793,108 serialized value bytes.
The default command reference and retrieved references account for 938,196 and
808,695 bytes respectively. The confirmed definition accounts for 426,870
bytes. These totals exclude field keys and provider thread history.

A trial extended identical-field references from parameters to the timeline,
sketches and bodies. Rebuilding the observation from each checkpoint produced
545,532 bytes before and after the change. The full observations carry native
details absent from the summaries, so this transformation offers zero savings on
the retained run. Keep the existing encoding. The next comparison should
measure the effect of sending static contract and command references once per
provider context while preserving a complete packet for offline replay.

Run `python -m tools.cad_packet_budget DOCUMENT/execution-checkpoints` to
measure the static-context opportunity. The 51 packets total 5,486,227 bytes.
Repeated values in seven stable contract and tool-reference fields account
for 1,906,400 bytes (34.7%). This is the gross upper bound before reference
overhead and context refreshes. The provider's retained history and token
accounting require separate measurement. Static reuse alone falls short of
the proposed 50% input reduction even at the application-payload level.

An offline replay through the implemented message cursor sent 3,591,853 bytes
of CAD JSON blocks across the same 51 decisions, down from 5,486,227 bytes
(34.53%). This comparison excludes image bytes, system instructions and
compaction refreshes. A compaction refresh restores exact sources once on the
same provider thread, including inline images. Provider tokens and elapsed
time still require a controlled live comparison.
