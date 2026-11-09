# Drawing 42 bore continuation

## Live outcome

Codex access recovered after the previous quota rejection. Calls 48–54 resumed
the original candidate. The straight entrance cut and the curved-bore profile
were accepted. The separate quarter-revolution cut reached a native Boolean
retry and was rejected by the intermediate history gate.

The original SolidCraft 0.28.0 executable remains selected. The confirmed
definition, nominal dimensions and acceptance tolerances remain unchanged.

## Reproduced cause

The exact rejected operation was replayed on an independent copy of checkpoint
`fba3c081785f4301a6f81b3a30d4d05a`. It reproduces the same history warning:

| Native observation | Value |
| --- | --- |
| Recovery strategy | `tool_nudge` |
| Tool translation | 0.0018293364698709746 mm |
| Tool rotation | 0.000002 rad |
| Warning | Boolean retry: tool displacement |

The cut guard passed its material-boundary checks. The subsequent history gate
detected the native warning. Its rejection preserves the requirement for clean
editable construction history.

## Alternative tested locally

Starting from pre-bore checkpoint `32c2bc57207d4cfb92a105c42d665bb4`, a single
continuous line/quarter-arc/line pipe cutter, extending 2 mm beyond each external
face, passes the overrun guard and creates a closed solid without a native
history warning.

| Measurement before bolt holes and finishes | Result |
| --- | --- |
| Analytic expected volume | 28575728.834156595 mm³ |
| Independently integrated STEP volume | 28575728.834156595 mm³ |
| Bounds | X −180…410, Y −180…180, Z 0…590 mm |

The reference calculation uses two rounded-square solid flanges, two exposed
straight sections of length 100 mm and a quarter-torus exterior. It subtracts a
Ø210 passage with total centerline length `300 + π × 260 / 2` mm.

The diagnostic path uses numeric seeds and remains underconstrained. Its model
is retained as diagnostic evidence. The specialist must build its own named,
parameter-driven, fully constrained path within the accepted construction chain.
Its eventual part still requires all hole, counterbore, finish and final checks.

Native XZ sketches use `x_dir=[1,0,0]`, `y_dir=[0,0,-1]`. The diagnostic explicitly
checked this basis before measuring the corrected path. Positive world Z maps
to negative sketch y for this plane.

## Repair evidence and continuation

Intermediate gate failures now expose the exact native feature warnings and
Boolean diagnostics in the next repair packet. The runtime validates the
rejected-observation path and SHA-256 before reading that evidence. A focused
controller suite passes 28 tests, including observation tampering rejection.

The scoped offline receipt is retained as
`execution-checkpoints/offline-diagnosis-bore-20261104.json`. It identifies its
source report, source hash, exact checkpoint, measured limits and remaining
qualification work. The model used an explicit revision decision to return to
the pre-bore checkpoint. Consumed calls and historic failures remain recorded.

Machine-local diagnostic evidence:
`/mnt/cold-hdd/bigbrain-local/cad/cad42-bore-diagnostic-4w8t83fy/`.

## Driving-path qualification

Call 57 proposed expression-based coordinate seeds without driving dimensions.
The sketch-quality gate rejected that path. Investigation also identified that
temporary `feedback` was cleared after a successful revision decision. Scoped
offline diagnostic receipts now remain in each subsequent decision packet,
including after read-only observations and restarts. Their paths, hashes and
contract identity are verified before inclusion.

The dimensioned alternative uses a first located line with a driving length, a
shared-endpoint arc with driving radius/sweep and a tangent constraint, followed
by a shared-endpoint line with a driving length. Native dimension placement can
introduce a construction axis and consume a curve ID. The pipe path must use
the actual observed non-construction curve IDs.

Two automated native cases at R30 and R260 check zero degrees of freedom,
connected endpoints, absence of blanket curve fixation, the observed XZ basis,
and both radius and lead-length edits. The controller/path suite passes 31
tests. A disposable copy of drawing 42 additionally passes the continuous cut
and independent volume checks after changing R260 to R266:

| Radius | Analytic volume | Independent STEP volume |
| --- | ---: | ---: |
| 260 mm | 28575728.834156595 mm³ | 28575728.83415658 mm³ |
| 266 mm | 28871816.96618928 mm³ | 28871816.966189533 mm³ |

The edited path remains fully constrained and its native history has no errors
or warnings. Evidence is retained at
`/mnt/cold-hdd/bigbrain-local/cad/cad42-bore-diagnostic-lgae33cr/`.
These are local operation checks; final qualification of the model-driven
candidate remains pending.

## Projected-reference quality gate

Call 58 supplied the correctly dimensioned path. Its rejection exposed a runtime
false positive: `locate:true` creates a fixed projected construction axis, and
the old blanket-fixation check rejected that reference alongside functional
curves. The check now recognizes fixed construction references with a matching
native projection link. Fixed functional curves, unlinked construction curves
and unknown projection kinds remain rejected.

The exact saved call-58 proposal passes native construction and full workflow
diagnostics against the confirmed drawing on an independent copy:
`/mnt/cold-hdd/bigbrain-local/cad/cad42-path-exact-replay-q8icro6j/`.

The workflow/controller/resource/path suite passes 53 tests after this change.
Hash-verified offline diagnostic receipts contribute to the evidence identity
used by the repeated-failure guard. This permits a retry after additional
verified diagnostic evidence while retaining rejection of unchanged retries.

## Model-driven continuation and hole provenance

The corrected path was accepted at checkpoint
`5670b0185c954d01b0725749a67c27ca`. The continuous bore was accepted at
`2cb65a197a6649bfa8438f5100cd9b19`. The four entrance-hole profiles were then
accepted at `25db834b39444a609f057c143cdc2f30`.

Call 64 placed a native timeline name in `CutIntent.feature_id`. The gate
rejected it before mutation. That field identifies a drawing feature, whereas
`command.params.name` identifies the native operation. The schema and error
message now state this distinction and list the available drawing-feature IDs.

Offline inspection also located the proposed boundary origins at the center of
the already empty passage. Opening anchors must lie on existing material on the
corresponding face. The four-hole extrusion passes locally with the original
geometry and targets, drawing feature `both_hole_patterns`, and material anchors
at `[-130,-130,0]` and `[-130,-130,50]`:

| Independent volume | Value |
| --- | ---: |
| Expected after four Ø30 through holes | 28434357.164745055 mm³ |
| Measured STEP volume | 28434357.164745018 mm³ |

Full workflow, cut safety and native history checks pass on that copy. Evidence:
`/mnt/cold-hdd/bigbrain-local/cad/cad42-hole-intent-replay-uar2wmjx/`.
The cut-safety/controller/workflow/path regression suite passes 68 tests.
