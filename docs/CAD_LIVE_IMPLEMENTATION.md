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

Local verification currently covers presentation persistence across store
recreation, conversation isolation, checkpoint identity protection and existing
native CAD integration. Live rendering and restart qualification remain pending.

The existing hosted viewer and worker changes are prerequisites already present
in this worktree. The completed branch will receive one final push. Merge follows
the repository owner's subsequent review.
