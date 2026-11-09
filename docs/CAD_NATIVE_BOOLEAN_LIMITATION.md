# Native curved pipe/flange Boolean investigation

## Observed failure

A hollow quarter-bend with a straight lead-in and an overlapping annular flange
fails native `solid.combine` union. SolidCraft CLI 0.28.0 and 0.30.1 both reject
the saved candidate. Reversing the target and tool also fails. The straight-pipe
counterpart passes.

The STEP export passes independent boundary-representation checks. OpenCascade
unites the same exported solids into a valid result, with volume matching the
analytic expectation. Export validity does not establish every invariant of the
native internal representation; the export/import path can represent topology
differently.

## Located failure path

The pinned upstream 0.28.0 source establishes this chain:

```text
solid.combine / native kernel Boolean
    -> truck_shapeops::or_with_history
    -> process_one_pair_of_shells
    -> create_loops_stores
       -> intersection curve construction / geometric vertex insertion
    -> None
    -> KernelError("no result")
```

Runtime tracing with `SHAPEOPS_TRACE=1` confirms failures tagged `intersection
curve`, `add_geom_vertex 1` through `4`, `loops stores` and `first shells` across
the retries. The preserved stderr is the transport's final 32,000-byte window.

In the source, intersection-curve construction can return `None` on degenerate
input or failed double projection onto the two surfaces. Geometric vertex
insertion can fail during curve/surface projection or edge splitting. Those
failures prevent construction of the intersection loops needed to divide and
classify faces. SolidCraft attempts multiple numerical/topological recovery
strategies before returning its final error.

This locates the failing subsystem and rules out a missing command description
as this failure's cause. The trace does not identify a unique offending face
pair or numerical singularity. Coincident boundaries are a plausible trigger,
supported by the successful feature-order/cutter experiments; proving the
specific convergence defect would require deeper kernel instrumentation.

Source pointers at tag `v0.28.0`:

- `crates/kernel/src/ops.rs`: `truck_boolean`, `boolean_whole_with`.
- `vendor/truck-shapeops/src/lib.rs`: `SHAPEOPS_TRACE` tracing macro.
- `vendor/truck-shapeops/src/transversal/integrate/mod.rs`: shell integration.
- `vendor/truck-shapeops/src/transversal/loops_store/mod.rs`: intersection loops
  and `add_geom_vertex`.
- `vendor/truck-shapeops/src/transversal/intersection_curve/mod.rs`:
  `IntersectionCurveWithParameters::try_new`.

## Native construction alternative

```text
Outer pipe + solid flange
          |
       native union
          |
Continuous bore cutter extending beyond both ends of the part
          |
       native cut
          |
Editable hollow part, checked against the original geometry
```

The cutter extends 2 mm outside each end in these qualification cases. This
extension belongs to the subtractive tool. The finished part retains its
specified exterior dimensions and bore. It avoids placing the cutter's end caps
exactly on the part's terminal faces. This is an operation-planning alternative;
there is no change to the Boolean kernel, model acceptance tolerances or
production measurement provider.

| Variant | Result |
| --- | --- |
| Hollow pipe joined to annular flange | Fails on the minimal curved case |
| Same union with operands reversed | Fails |
| Exterior union, then flush-ended bore | Passes at R30 and edit R36; fails at R60 |
| Exterior union, then extended bore cutter | Passes at R30/R60 and edits R36/R66 |

The passing extended-cutter cases check:

- one closed solid and exact-surface export validity;
- expected envelope and independent analytic volume;
- sampled empty material at the flange bore, curved bore and outlet;
- retained material in the curved wall and flange;
- native feature history, including `ContinuousBore`, with no feature errors;
- regenerated geometry and the same checks after changing the bend radius.

These results qualify this bounded construction pattern. Other flange layouts,
curved profiles and finish operations require their own cases. The complete
drawing 42 still requires reconstruction and end-to-end verification through
BigBrain. Automatic selection of this alternative by the specialist remains
unqualified.

## Retained evidence

Machine-local root: `/mnt/cold-hdd/bigbrain-local/cad/`.

- `union-kernel-trace-e8mbp6p2/`: original native case, tool results and internal
  shape-operations stderr tail.
- `union-reverse-ri0zal68/`: reversed-operand failure.
- `union-outer-before-bore-eu7njro6/`: first exterior-first success.
- `operations-exterior-first-20261102-results.xml`: flush-ended bore comparison,
  including the R60 failure.
- `operations-exterior-extended-local-20261102-results.xml`: two extended-cutter
  cases pass, each including its parameter edit and local material checks.
- `operations-exterior-extended-local-20261102/`: native models, STEP exports,
  measurements, local probes and timeline inspection for those cases.

The original failing tests remain in the qualification suite. Retest them on
future SolidCraft versions. Once the original route passes the same geometric
and edit checks, reassess the workaround and its version-specific guidance.
