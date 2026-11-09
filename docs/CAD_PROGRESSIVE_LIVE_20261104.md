# Progressive CAD qualification — drawing 42

## Outcome

The supplied drawing reached five accepted native construction checkpoints.
The complete flanged elbow remains incomplete. Whole-part inspection, final
exports, bore continuity, bolt patterns and finishing are still pending.
The original R260 centerline interpretation and dimensional requirements remain
unchanged. Qualification uses Codex Sol 6.1 low through the browser on port 3134.

| Retained step | Native outcome |
| --- | --- |
| `bride_entree_profil_numerique` | Rounded flange sketch; functional driving dimensions; zero remaining DOF |
| `bride_entree_extrusion` | First solid flange |
| `profil_raccord_entree` | Constrained circular connection profile |
| `raccord_droit_entree` | Straight exterior connection |
| `profil_coude_exterieur` | Constrained exterior bend profile at Z=150 |

Checkpoint root:
`/mnt/cold-hdd/bigbrain-local/cad/drawing117-live/d4f8d16c0e884319b9df205f76f19943/execution-checkpoints/`.
These states are intermediate evidence; the delivery gate remains closed.

## Observed causes and corrections

```text
Runtime-checked contract confirmation
                  |
       ExecutionAuthorization
       contract + definition + candidate
                  |
          Controller decision packet
       /              |              \
accepted_workflow   last_action   protocol_diagnostics
       \              |              /
         proposed command group
                  |
       scope / input / solver checks
                  |
       native checkpoint or diagnosis
```

1. **Repeated confirmation.** The specialist returned a proposed contract through
   `blocked`, despite the recorded UI confirmation. The original objective still
   contained the request to propose a contract. The worker now supplies an explicit
   runtime authorization bound to the exact contract, definition and candidate.
   Mismatches are rejected before execution. Later live decisions began construction.

2. **Reference loop.** Fourteen consecutive decisions requested the same pair of
   native descriptions; the first retrieved them and thirteen repeated that read.
   Cached descriptions existed, while the packet lacked an explicit completed-action
   result and retained only the latest protocol rejection. The controller now carries
   action outcomes, retained protocol diagnostics and completed native references.
   A repeated fully satisfied request receives an actionable diagnostic; another
   identical rejection stops the run. Subsequent live calls progressed to geometry.

3. **Omitted accepted parameters.** Extrusion proposals omitted the existing workflow
   parameter inventory. Native parameter values lacked the complete provenance and
   dependency declarations required by the guard. The packet now includes the exact
   accepted workflow. Diagnostics distinguish omissions from modified declarations.
   Conservation checks remain enforced. The subsequent live extrusion was accepted.

4. **Native axis-origin fallback.** The model supplied
   `axis.origin: ["elbow_axis_radius", 0, "end_tangent_distance"]` to `solid.revolve`.
   The accepted profile plane was actually Z=150. In pinned 0.28.0 source
   `crates/engine/src/cmd/features.rs::axis_param`, numeric conversion failure falls
   back to the world origin. The native revolution then reported that its axis
   lay outside the sketch plane. BigBrain now rejects this input before mutation,
   including in the progressive preflight before charging a native repair.
   The underlying native parser remains unchanged.

## Qualified native axis alternative

Two parameter-driven offset datum planes define a named intersection axis via
`construct.axis.two_planes`; `solid.revolve` references that axis by name.
The isolated native test passes independent quarter-bend volume and bounds,
zero-DOF profile checks, a radius edit from 260 to 280 mm, and an axial-plane edit
from 150 to 170 mm. The final edit shifts the measured geometry by 20 mm.
The feature chain remains native and editable. Rotation orientation must still
be observed for the intended part. Combined flange/bend/finishing interactions
retain their separate qualification gate.

## Resource and evidence ledger

| Ledger | Consumption and scope |
| --- | --- |
| `calls-cut-safety-20261103.json` | 48 calls, 1102.9 s inference; includes 27 calls preceding this progressive qualification and the failed entry/reference sequence |
| `calls-progressive-20261104.json` | 15 calls, 234.8 s inference; preserves the initial 12-call segment and its continuation under the campaign margin |

Both ledgers remain under
`/home/kwestog/Documents/code/tests/cad-drawing117-live-20261101/`.
The second ledger's cumulative ceiling is 48 calls and 1200 s inference. The
run stopped at its contract's native repair allowance before reaching either
ceiling. Three native rejections are retained: two invalid sketch point inputs
and the axis-origin failure. Counts and failed evidence remain unchanged.
Resume now checks an exhausted allowance before issuing another model call.
API-equivalent token cost is unestablished by these ledgers.

Local evidence under `/mnt/cold-hdd/bigbrain-local/cad/`:

| Evidence | Scope |
| --- | --- |
| `progressive-safety-final-20261104.xml` | 81 passing controller, capability, worker, recovery and native transport tests |
| `progressive-workflow-handoff-20261104.xml` | 15 passing controller tests, including omitted-inventory recovery |
| `progressive-read-recovery-20261104.xml` | Duplicate-reference stop and native rounded-profile edits |
| `rounded-profile-original-20261104.xml` | Rounded-profile case also passes on the original executable |
| `parametric-revolve-axis-20261104.xml` | Named datum-axis alternative, exact-surface measurements and parameter edits |

## Remaining gates

The subsequent [local axis diagnosis](CAD_AXIS_CONTINUATION_DIAGNOSIS_20261104.md)
reproduces the next positive-angle revolution successfully on disposable copies
and identifies missing observation coverage in the controller. It issues no
provider calls and preserves the accepted six-checkpoint candidate.

### Explicit resource continuations

The subsequent four-call authorization preserved the five accepted checkpoints,
37 consumed controller decisions and three native failures. The runtime binds
the continuation to the contract, definition, candidate and executable hashes.
Each decision reserves its call before inference; restarting preserves consumption.
The campaign ledger also caps all provider calls, including final inspection.

Calls 16–19 retrieved the datum-axis reference, constructed a named parametric
axis as a sixth accepted checkpoint, recorded one cancelled call during an
operator server restart, and inspected the resulting design. The cancellation
remains charged. No additional native failure occurred. The part remains incomplete.

A further two-call authorization begins at controller decision 41 and campaign
call 19. It references the preceding authorization hash and retains its baseline
and evidence. Renewal replay, candidate mismatches and counter resets are covered
by offline controller tests. The controller, recovery and worker suites passed
60 tests before this continuation; the renewed controller suite passed 19 tests.

The retained candidate uses the original 0.28.0 executable with SHA-256
`8d67a0d09eb41232268b73406d660ce5d50894d0a42f1ff506bf17704f841350`.
The separately qualified helix executable remains selected in local configuration
for other candidates. This campaign overrides that selection to preserve its
existing engine-bound checkpoint chain.

Calls 20–21 completed a parameter-graph observation and a precise-geometry
capture. Both returned successfully. The sixth checkpoint remains the head;
the model has yet to propose the bend revolution. The campaign stopped at its
21-call ceiling, with 280.3 s cumulative inference and three historical native
failures. No final delivery or whole-part qualification is established.

The current candidate exhausted its renewed call allowance. Continuing its
execution needs an explicit renewed resource decision; the runtime preserves the
six accepted checkpoints. The datum-axis method still needs to be applied through
the model to the complete part, followed by independent inspection and any
authorized repairs. The other supplied complex drawings and Windows execution
remain open. This campaign supplies partial live evidence for progressive
construction and recovery.
