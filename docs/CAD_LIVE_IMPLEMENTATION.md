# CAD construction in the Atelier

## Delivery scope

The Atelier follows accepted construction checkpoints in two compact modes.
The solid view shows the developing geometry. The construction view additionally
shows sketches, reference planes and construction elements. A separate action
opens the full SolidCraft interface in the main workspace.

The conversation owns the execution, document, revisions and evidence. Published
delivery checks remain attached to the exact verified source hash.

## Milestones

1. Persist the working presentation identity before broadcasting progress.
   Resolve its native artifact through the accepted checkpoint chain and enforce
   conversation ownership and artifact hashes on every read.
2. Present accepted checkpoints during real CAD brain construction. Preserve the
   camera and responsiveness while preparing the next geometry in a worker.
   Coalesce superseded presentation requests and reject stale completions.
3. Provide solid and construction preview modes, plus the full editor action.
   Keep one document identity across these surfaces and retain exclusive editing
   ownership during agent construction.
4. Restore the conversation's CAD runs and Atelier after server restart. Expose
   CAD checks and retained attempts through Evidence. Qualify this through the
   normal application entry point.

## Current implementation evidence

The first increment records `working-state.json` under the owned document before
progress reaches subscribers. It carries the execution context and presentation
state. Accepted checkpoint resolution validates the engine and contract lineage
and verifies observation hashes. The working artifact endpoint requires the
explicit current checkpoint and uses the existing owned-artifact reader.

The compact viewer prepares native checkpoints through the qualified worker and
retains its iframe and camera. Its presentation queue coalesces intermediate
requests while geometry is prepared. Solid and construction modes share this
viewer. Construction mode explicitly shows accepted sketches and dimensions.
The expanded observation mode exposes the full SolidCraft shell during agent work.

Each run has a retained presentation record. Conversation history supplements
the bus journal from these records and marks pre-restart work interrupted.
Terminal CAD outcomes publish immutable manifests into the common evidence
repository with their source hashes and measured criteria.

The preview host remains mounted across overview, part and full observation
surfaces. Its camera and compact mode survive these transitions. CAD overview
widgets use one full-width column, with verification following the model.
CAD navigation exposes one primary Piece tab and a Verification tab when checks
are available. Previously retained CAD and overview routes resolve to the same
piece presentation. Preview mode selection stays visible in compact and expanded
layouts, including a return from the full observation shell.

## Qualification

The normal web application was exercised with an artificial constrained plate
and recorded provider decisions. CadBrain executed four native groups, including
the hole sketch and through cut. The browser displayed the third accepted group
while construction was still running, including the sketch and driving dimensions.
The resulting delivery passed its envelope, cut-safety and design-quality checks.
This campaign exercised transport and presentation with recorded decisions.
Model interpretation quality remains covered by the earlier CAD qualification.

After the server process ended, a new process opened the same retained stores.
The conversation reopened its Atelier and the Evidence page displayed the CAD
run and checks. Switching overview, part and full observation preserved the same
native iframe identity. The selected Construction mode survived the round trip.
DOM measurements confirmed equal model/verification widths and a verification
card below the model. Browser screenshots are retained locally under
`/tmp/cad-live-intermediate.png`, `/tmp/cad-live-construction-after-restart.png`
and `/tmp/cad-atelier-stacked-verification.png`.

The frontend suite passes 179 tests and its production build completes. The
expanded CAD/backend campaign passes 392 of 396 tests. Four native operation
qualifications retain the previously observed limits in the unchanged geometry
adapter and qualification cases.

| Native case | Observed failure |
| --- | --- |
| Quarter-bend pipe/flange union | Native union returns no result |
| Parameterized coil | Volume 394.772099729 versus 394.784176044 mm³ at the existing tolerance |
| Flush cutting tool at 60° | Native pipe cut returns no result |
| Extended cutting tool at 60° | The inlet opening fails the outward material boundary check |

## Remaining integration boundaries

The full observation shell retains read-only geometry ownership. Interactive
manual editing and its transfer back to the worker require their own qualified
handoff. The browser campaign was observed on Linux. Windows execution remains
to be qualified against the shared behavior and storage contracts.

The existing hosted viewer and worker changes are prerequisites already present
in this worktree. The completed branch will receive one final push. Merge follows
the repository owner's subsequent review.
