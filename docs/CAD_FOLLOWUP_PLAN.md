# CAD follow-up

Concrete phases and exit criteria: [CAD web action plan](CAD_WEB_ACTION_PLAN.md).

## 1. Tracking consistency

Use the verified published revision as the current delivery across the workshop,
chat summary and activity view. Preserve the original attempt status, diagnostic
and steps in an explicitly labelled history. Reconciliation requires matching
session and document identity, monotonic revision and checks bound to the native
artifact hash. A running attempt keeps its live state until completion.

Milestone: an independently published delivery resolves a failed attempt across
all persisted UI mirrors; reload and stale responses preserve the same outcome.

Implementation: publication reconciliation updates the shared run records and
retains the previous attempt diagnostic, steps and completion timestamp. Terminal
event replay preserves the published verdict. The preview notice sits below the
viewer, leaving its controls accessible.

Validation: all 168 frontend tests pass and the production build passes. A browser
fixture uses the real retained drawing 42 revision 14 and a reconstructed failed
attempt. Workshop status, chat summary and journal show the verified publication;
the previous 64-check diagnostic remains in attempt history. This verifies UI
reconciliation and artifact reads. Model execution is outside this check.
Screenshot: `/tmp/cad-tracking-proof.png` (local temporary evidence).

## 2. Live CAD workspace

Define the SolidCraft integration boundary and progressive 3D/2D observations.
Design the workspace switch, checkpoint display and future assembly support
before implementation. Keep the current SolidCraft version and qualify future
versions through the existing engine and measurement adapters.

Local 0.28.0 source inspection confirms a browser application with
`window.solidcraft.request`, `execute`, `commands` and `inspect`. These share the
desktop command handlers and undo history. The browser uses a virtual filesystem;
hidden tabs can delay requests and reloading ends pending work. The local source
files `docs/browser-api.md` and `apps/solidcraft-web/src/api.rs` have no local
changes against the pinned checkout.

Next milestone: qualify a locally served browser build against the same native
document: load, inspect named history, change a parameter, undo, save and reopen.
Measure startup and switching latency and compare geometry. This determines the
embedded editor boundary before integrating it into the Atelier. Establish one
authoritative editing session and explicit ownership while the agent operates.

Progressive preview should consume accepted checkpoints with document, revision
and source hash identity. Intermediate states show construction progress; the
existing delivery gate supplies the final verdict. Qualify the 3D and sketch views
on the same checkpoint, plus reconnection, rollback and switching behavior.

## 3. Additional drawing qualification

After workspace integration, qualify one or two further drawings already supplied
by the user. Select the cases together before starting the campaign. Keep their
source dimensions, necessary clarifications and local-detail checks explicit.
Record autonomous progress, interventions, repairs, usage and the final measured
outcome. Passing drawing 42 alone establishes a limited part of CAD capability.

## 4. Assemblies

After the additional drawing campaign, qualify component identities, instances,
placement constraints, interference checks and revision propagation on a simple
assembly. Extend toward articulated mechanisms as a subsequent capability.

## 5. Production architecture

Study user identity, access rights, project isolation, usage accounting, costs,
administration and diagnostics. Architecture and commercial choices require a
dedicated discussion before implementation.

## Browser execution direction

Production BigBrain orchestration and proprietary decision logic run on the
server. SolidCraft geometry commands execute in the client browser through
WebAssembly; WebGPU handles rendering. The integration must expose this boundary
through replaceable adapters. Progressive updates must retain the
viewer and camera, prepare geometry ahead of scene swaps and use smooth,
interruptible transitions with reduced-motion support.

The pinned 0.28.0 browser package compiles the engine and UI to WebAssembly.
Rendering uses WebGPU with a WebGL2 fallback. This supports client-side CAD
execution: a service distributes the application assets while the user's machine
performs geometry and rendering. Model inference, accounts and server-held
verification remain separate resource decisions.

Prefer evaluating a version-pinned browser distribution served with BigBrain.
Embedding the public upstream app would introduce cross-origin communication and
upstream version changes. Qualify browser memory, responsiveness, native-file
round trips and the effect of the isolated native helix patch before selecting
the authoritative execution path. Desktop and browser adapters must share the
document and evidence contracts.
