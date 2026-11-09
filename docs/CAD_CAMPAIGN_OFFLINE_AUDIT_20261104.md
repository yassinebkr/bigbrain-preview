# Offline audit of the 19-call CAD campaign

## Evidence boundary

This audit examines calls 26–44 of `calls-progressive-20261104.json` and the
corresponding retained drawing-42 decision packets. It issues zero provider
calls. Native reproduction uses disposable copies on the cold disk and the
candidate's original 0.28.0 executable. The accepted candidate retains eleven
checkpoints throughout the audit.

## Call accounting

| Calls | Observed work | Finding and action |
| --- | --- | --- |
| 26, 33, 36, 39, 41 | Five accepted construction groups | Retain their actual native evidence |
| 32 | Rejected extrusion from a face | Undeclared implicit sketch; reproduce rejection and improve diagnostic |
| 27, 29, 30 | Three rejected precise-measurement requests | Existing-body target was incorrectly refused; target matrix now covers this combination |
| 28, 34, 38, 40 | Four native topology requests | Supply this evidence locally before the next model decision |
| 31, 37 | Exact measurements after solid mutations | Fresh geometry evidence justified |
| 35 | Exact measurement after a sketch-only step | Candidate for future reuse; cross-checkpoint equivalence remains unqualified |
| 42, 43 | Source interpretation and clarifications | Outstanding source questions; no CAD construction dispatched |
| 44 | Front decision deadline | Accepted transport turn produced no final decision before 120 s |

The campaign therefore contains six construction proposals, ten observation
requests and three initial front decisions. Three observations failed due to a
controller interface defect. Four topology results can be obtained by deterministic
local tool calls. These facts identify avoidable model-mediated work. They do not
measure the number of decisions a future live model will actually choose.

The two later source-interpretation requests correctly remain separate from
whole-part construction qualification. No complete part was established by
the campaign or this offline audit.

## Runtime correction

```text
Accepted native checkpoint
        |
        +-- observed design and parameter graph
        +-- local native topology for every current body
        |
Decision packet with checkpoint-bound evidence
        |
Model construction or genuinely new evidence request
        |
Native execution and intermediate checks
        +-- accepted checkpoint
        +-- rejected inventory + named diagnostics + retained observations
```

The driver now reads `body_topology` locally before a model decision when that
body lacks evidence for the current checkpoint. Cached results at that checkpoint
are reused. A new checkpoint triggers a fresh native read; matching volume or
bounds cannot authorize reuse across revisions. The returned body identity is
checked before the result enters the packet. This shared behavior applies across
Linux and Windows; native Windows execution remains unqualified.

Observation target validation is factored into a single function with a matrix
covering all five tools, existing/unknown targets and incompatible target kinds.
Precise measurement accepts an existing body in its question and retains an
explicit whole-document measurement scope.

Intermediate inventory failures now name the undeclared objects and preserve
`rejected-observations.json`, its SHA-256 and the actual sketch/history/body
inventories before restoring the accepted prefix. Safety and delivery checks
retain their original requirements.

## Exact-trace reproduction

The original four topology requests were replayed on their actual saved native
checkpoints. The runtime supplied `Coude_42` topology with 21, 21, 23 and 23 faces,
respectively, before any model inference.

The exact call-32 face extrusion was then replayed using a recorded-decision
adapter. It reproduces the intermediate rejection and now reports:

```text
Observed sketches contains undeclared construction objects: Sketch1
Observed timeline contains undeclared construction objects: Sketch1
```

The rejected-state record contains `Sketch1` and `Raccord_droit_sortie` alongside
the previously accepted inventory. Recovery preserves the seven-checkpoint prefix
of this disposable reproduction. The original candidate's controller and head
hashes remain identical to their pre-audit values. Two synthetic adapter decisions
were used; neither contacted a model or consumed provider credits.

Evidence:

- `/mnt/cold-hdd/bigbrain-local/cad/campaign-offline-replay-9e9ni_12/audit.json`
- `/tmp/cad_campaign_offline_replay.py`
- `/tmp/cad-campaign-offline-corrections-20261104.xml`: 109 passing focused tests
- `/tmp/cad-observation-efficiency-20261104.xml`: 18 observation/repair regressions

## Cross-checkpoint measurement reuse

The saved bend and subsequent outlet-sketch checkpoints have identical
`cache/bodies.bin` payload hashes. SolidCraft's pinned native-cache implementation
stores exact B-rep body data in that payload, with body placement and evaluated
state associations in the manifest. A payload hash alone therefore cannot serve
as a revision-equivalence proof. The current correction keeps precise-measurement
reuse scoped to the checkpoint. Production reuse across sketch-only changes needs
its own geometry/placement identity contract and qualification.

## Rectangular-elbow deadline

The transport trace for turn `6bad6403ad254830b1d55966613550b5` records:

| Event | Elapsed time |
| --- | --- |
| Native thread ready | 84 ms |
| Native turn accepted | 91 ms |
| Interruption requested | 120000 ms |
| Interruption acknowledged | 120004 ms |
| Local terminal trace | Deadline; usage unknown |

Connection establishment consumed under 0.1 s. The recorded trace provides no
completed response, token usage or intermediate response-byte evidence for the
remaining interval. It cannot distinguish slow generation from a remote turn
stall. The UI did settle into its explicit timeout message. This audit changes
neither the timeout nor the model and issues no identical live retry.

Trace:
`/home/kwestog/Documents/code/tests/cad-drawing117-live-20261101/evidence/inference/e72f56c8fc1e4138a97481059dfea940.jsonl`.

## Remaining limits

The offline evidence establishes corrected tool-target handling, native topology
availability and actionable rejection diagnostics. It does not establish live
token savings, complete drawing-42 delivery or successful construction of the
other supplied drawings. Source clarifications remain open. Further inference
requires a separate decision after reviewing these outcomes.
