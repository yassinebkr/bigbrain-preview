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

## Regression checkpoint

On Linux, the pinned SolidCraft build passed 20 tests spanning CAD execution,
presentation persistence, the browser bridge API and inference-free recovery
of a retained inspection. Reproduce with the qualified CLI on your platform:

```text
python -m pytest -q tests/test_cad_live.py tests/test_cad_inspection_replay.py tests/test_cad_execution.py tests/test_cad_browser_api.py
```

For the next controlled live run, record role/model/effort, drawing digest,
engine digest, call limit, inspection reserve and whether any operator recovery
was required. The primary acceptance result is autonomous publication with the
same dimensional and cut-safety requirements. Compare the token and inference
totals with the reference table separately from end-to-end wall time. Record
quota interruption and incomplete delivery explicitly. The first model
response, first accepted solid and first verified delivery are distinct events.

A second reconstruction recalculated all 28 retained section probes on the
rebuilt and published STEP files. All intervals matched and all probes
returned conclusive results. Use
`--reference-sections DOCUMENT/revision-5/sections.json` together with
`--reference-step`. The tool still reports the four intermediate cut file
digest differences independently of the successful geometric comparisons.

## Sol 6.2 low live probe

The probe ran directly through CadBrain with the previously confirmed drawing
definition, exact image and pinned native engine. It started from a blank
document. The 20-call probe reserved two calls for closing and inspection and
stopped when the construction share ran out. The remaining calls were unused.
The probe wrapper rejected the next construction request locally, after the
runtime opened its trace, so the extra failed trace consumed no provider call.

- 18 provider calls reported 1,724,778 input tokens, including 970,112 cached,
  and 14,295 output tokens.
- Cumulative provider-call time was 459.06 seconds. Worker wall time was
  488.04 seconds. Chat intake and browser presentation were outside this run.
- The controller retained 13 accepted checkpoints, through the first flange's
  counterbore profiles. No verified delivery was produced.

This measures an incomplete run. Cost and duration per verified delivery
remain unknown. For future probes, the runtime should receive the construction
share up front so that the reserved phase receives the correct checkpoint
without first attempting a construction call that the wrapper will reject.

### Grouped sketch replay

On a disposable copy of the Sol probe, the 18 retained native commands for
flange A holes, flange B holes and flange A counterbores reproduced the three
sketch groups in one accepted group. The production intermediate validator
passed. The resulting design inventory, parameter graph, cut evidence and
remaining obligations matched the last original checkpoint. This establishes
that the runtime can replace three proposal turns with one for this retained
sequence. The model's ability to choose the combined group in a fresh run
still requires live verification.

### Intermediate cut digest diagnosis

The byte audit compared the four retained and rebuilt `before.sc` and
`cutter.step` pairs for groups 18, 21, 24 and 27. The SolidCraft ZIP archives
had identical non-cache entries, including byte-identical `document.json`.
The differing entries were `cache/model.json` in all four pairs and the two
thumbnail entries in group 18. The STEP files differed exclusively in the
generated `CutSafetyTool_<id>` name on the `MANIFOLD_SOLID_BREP` entity. Replacing
that name in the diagnostic comparison produced byte-identical STEP data in
all four cases. The replay tool continues to report raw digest differences.
Every retained artifact remains verified against its original byte hash.

The replay tool now checks both original and rebuilt byte hashes before
comparing the documented serialization differences. It accepts only the
known native cache entries and generated STEP solid names as equivalent.
The Drawing 42 replay exited successfully with all 29 groups and 28 section
probes. Pass `--require-identical-cut-bytes` to require byte-for-byte equality
between the original and rebuilt intermediate files.
