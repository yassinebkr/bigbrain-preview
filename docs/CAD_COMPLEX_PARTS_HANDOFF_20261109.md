# CAD integration handoff

## Delivered scope

The CAD worker has progressive native construction, named parametric history,
checkpoint recovery, guarded material removal, bounded evidence transport and
independent geometry inspection. Executable fingerprints bind resumptions to the
qualified engine build. Recovery metadata distinguishes actionable resumptions
from situations requiring diagnosis or additional authorization.

```text
Confirmed definition
        |
Progressive construction -> accepted native checkpoints
        |                         |
        |                   retained-response replay
        v
Independent inspection -> measured criteria + runtime safety/quality checks
        |
Delivery gate -> versioned artifacts -> Atelier published-result reconciliation
```

## Evidence

- Drawing 42 revision 14 passes 66 measured checks and was published through the
  regular delivery gate. Two local through-hole probes originally encountered
  remote elbow material; the inspection was corrected to test the contractual
  flange spans consistently for all eight holes. Original results and span
  derivations remain available in the local campaign evidence.
- The final outlet chamfer was replayed from its paid, retained proposal through
  normal execution checks, with no additional model call or counter reset.
- Published-result reconciliation preserves the failed task history while
  displaying a separately verified delivery. Relocated storage pins the
  configured root and retains inner artifact identity/hash checks.

The [retained status](CAD_DRAWING42_STATUS_20261109.md) records hashes, counts,
diagnoses and the sequence of corrections. Local campaign artifacts remain
outside the repository.

## Remaining qualification limits

The complete local pre-merge suite ran 2,396 selected cases: 2,385 passed,
eight skipped, and three native operation cases failed. These are the retained
curved pipe/flange union and the flush/extended R60 bore routes in
`test_cad_operation_qualification.py`. Their assertions remain active and their
capabilities remain unqualified. GitHub runners have no SolidCraft installation;
native cases use the explicit installation prerequisite and are reported skipped.

- Drawing 42 completion included operator-led diagnosis, response replay and
  inspection-scope correction. This establishes this candidate's measured
  outcome; unattended completion of arbitrary drawings remains unqualified.
- Drawing 83, drawing 90 and the other attached complex parts still require
  their own campaigns. Full native-tool coverage remains incomplete.
- The isolated helix kernel correction has its own scope and qualification
  records. Drawing 42 retained the original executable. Future upstream-native
  replacement requires replaying the corresponding acceptance cases.
- Windows native execution, desktop handoff and metrology require Windows
  qualification. Shared contracts alone do not establish that evidence.
- Recovery states requiring diagnosis or authorization remain conservative.
  Retained-response replay is an explicit operator action; the UI does not
  automatically replay a rejected response.
- Nominal CAD geometry and sampled/local measurements do not establish
  manufacturing certification or universal geometric correctness.

## Next discussion

Pause further implementation after integration. Decide the next project priority
with the measured CAD scope and remaining portability backlog visible. Additional
CAD qualification and broader architecture changes require separate decisions.
