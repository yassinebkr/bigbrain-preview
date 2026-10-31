# Interactive CAD workspace

## Starting point

The first CAD cycle provides headless SolidCraft execution, measured criteria,
immutable revisions, STEP/STL exports and a revision-bound PNG in the Atelier.
The model-led plate probe qualifies the integration path. Richer geometry and
editing behavior require the acceptance campaign below.

## Implementation checkpoint — 31 October

- Installed 0.28.0 alongside 0.25.1 and verified its published SHA-256.
- Selected 0.28.0 as the Linux fallback engine; explicit executable configuration
  and PATH retain precedence. Active execution requires engine version 0.28.0.
- Sixty CAD contract, transport, real-engine integration and desktop-launch tests
  pass. The frontend has 149 passing tests and a successful production build.
- The Atelier uses a lazy STL viewer with orbit, zoom, fit, PNG fallback, bounded
  input and GPU-resource disposal. Rendering occurs on interaction and resize.
- One icon-only download menu exposes native, STEP and STL. A local-only GUI
  endpoint verifies the selected artifact, creates a private working copy and
  invokes the native executable with an argument array.
- Browser validation uses deterministic planning with actual SolidCraft
  geometry: a support with two through holes, measured volume 14,060.764 mm³,
  real mesh rotation, enlargement, artifact menu and GUI launch request.
  This journey consumes no model credits. Screenshot: `/tmp/cad-interactive-proof.png`.
- The initial browser fixture inherited PATH links to 0.25.1. Explicit-path 0.28
  engine tests passed separately. System links now target 0.28; the browser journey
  was repeated and its captured engine version checked before retiring 0.25.1.
- Updated Linux Applications and desktop launchers to 0.28.0. A direct GUI launch
  initialized Vulkan and its local control server; confirmation of the visible
  desktop revision remains a native acceptance step.

Remaining qualification: native Windows execution, explicit WebGL-loss and
task-switch browser cases, GUI working-copy edit/reimport semantics, and the richer
model-led campaign. The existing plate/enclosure/edit engine tests establish the
native adapter behavior independently from planning quality. This branch remains
open while those acceptance cases are completed.

## Phases and milestones

### Engine qualification first

Target SolidCraft 0.28.0 for this cycle, following the user's decision on
31 October. Install alongside 0.25.1 during qualification, verify the official archive checksum, then
run headless command, measurement, native reopen, rollback, export and GUI tests
before changing the default. Existing disposable fixtures can adopt format 45;
preserve their originals for comparisons. Versions 0.27.x and earlier cannot open
documents saved by 0.28.0.

Migration checkpoint: CLI PATH links and both Linux desktop launchers now select
0.28.0. The active adapter and planning prompt require 0.28.0. The replacement
browser capture records that exact engine version. Retire the old installation
after this checkpoint; historical qualification documents retain their original
version numbers. Desktop handoff is verified as a launch request with a private
copy; native visual confirmation and Windows qualification remain separate.

Relevant upstream changes include strict parameter checks for calls forwarded to
the GUI, corrected circle-length measurement, improved model caching and rendering,
and print-face metadata. The 0.26 release also updated ZIP handling for a critical
advisory. GUI features require explicit tool-surface qualification before agents
can rely on them. Updating the engine alone leaves the Atelier viewer unchanged.

Sources: [0.26.0](https://github.com/tangency-labs/solidcraft/releases/tag/v0.26.0),
[0.27.0](https://github.com/tangency-labs/solidcraft/releases/tag/v0.27.0),
[0.28.0](https://github.com/tangency-labs/solidcraft/releases/tag/v0.28.0).

| Phase | Implementation | Exit evidence |
| --- | --- | --- |
| 1. Compact artifact actions | One icon-only Download button with accessible label, tooltip and native/STEP/STL menu; explicit export errors | Keyboard navigation, focus return, readable theme, current-revision downloads |
| 2. Native GUI handoff | Shared launch request bound to document/revision/hash; Linux and Windows launcher adapters; open a dedicated working copy | Correct saved revision opens; missing application and stale hash fail clearly; source revision stays intact |
| 3. Interactive piece surface | Lazy-load a local mesh viewer from the captured STL; orbit, zoom, fit/reset, compact and enlarged views; retain PNG fallback | Actual artifact rendered; revision switching, cancellation, empty/malformed mesh, resource cleanup and reload tested |
| 4. CAD capability campaign | Perforated support, hollow enclosure, parametric edit preserving existing features, invalid operation and contradictory criterion | Independent dimensions/volume/body assertions, native reopen, STEP round trip, prior revision preserved on failure, browser journey |

## Behavioral contracts

### Artifact menu

Download actions use the currently displayed revision. One discrete icon opens
the format choices. Labels identify editable native, STEP and STL formats. The
menu follows the existing Atelier styling and remains accessible without hover.

### GUI handoff

```text
Displayed revision → scoped launch request → verify native hash
                                               ↓
                                  create dedicated working copy
                                               ↓
                                  native platform launcher
                                               ↓
                            external editing / explicit reimport later
```

The server accepts document identity and revision; it resolves all paths itself.
The launcher receives an argument array and uses the installed SolidCraft binary.
A local-user gesture initiates launch. Expose capability availability per platform.
The first handoff opens a working copy. External edits become a separate candidate;
reimport and verification need an explicit later action before publication.
GUI launch success means the process accepted the request; visual opening requires
native manual evidence on the platform being qualified.

### Viewer

The mesh is a presentation of the saved revision. Measurements and acceptance
continue to come from the native geometry evidence. A mesh cannot establish wall
thickness, mechanical strength or manufacturing safety. Enforce bounded artifact
size and triangle count, dispose GPU resources on revision changes/unmount, and
show an explicit fallback when WebGL is unavailable. Camera movement stays local
and consumes no model calls. Avoid continuous polling or rendering while hidden.

## Acceptance and sequencing

Implement offline/UI gates before paid model probes. Run real-engine cases and
one browser journey per interaction family. Request a separate bounded budget for
any additional model-led live campaign. Native Windows qualification requires a
Windows host; report its status independently from Linux.

Photos, diagram interpretation, attached CAD imports, printer operation and
broader workspace redesign remain later cycles. Track integration friction in
the existing workspace redesign backlog.
