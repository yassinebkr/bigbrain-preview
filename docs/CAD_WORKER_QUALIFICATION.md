# CAD geometry worker qualification

## Result and scope

The isolated SolidCraft 0.28.0 engine completes drawing 42 loading, a parameter
edit, undo, native save and reopen inside a dedicated browser Worker. The host
page accepts clicks throughout the run. Geometry, named feature history,
parameters and sketch solver states pass comparison with retained native
evidence. The saved document reopens in the installed native engine.

This qualifies computation isolation. The existing SolidCraft GUI still owns
its own synchronous session. Production integration requires a shared document
authority and a renderer handoff. The probe has no production command endpoint.

## Observed run

| Operation | Time |
| --- | ---: |
| Initial drawing 42 evaluation | 36.759 s |
| Initial measured inspection | 5.351 s |
| Flange thickness change, 50 to 51 mm | 35.689 s |
| Inspection after edit | 5.174 s |
| Undo | 1.7 ms |
| Native checkpoint save | 66.7 ms |
| Reopen worker checkpoint | 35.9 ms |
| Inspection after reopen | 5.164 s |

Maximum host animation-frame gap: 13.9 ms across 12,733 sampled frames.
Two response clicks are retained in the report. These measurements come from a
single local Chromium 155 run. WebGPU rendering was separately observed in the
user's Vulkan-configured Chromium 154. Combined engine/editor/render behavior
remains to be qualified.

The worker preserves 29 named operations and 11 solved, zero-DOF sketches.
Existing comparison tolerances remain 1e-7 relative native volume and 0.001 mm
bounds. These engine measurements complement the independent analytic STEP
delivery checks. The qualification comparator passes; six regression tests
exercise preservation, corrupted results, incomplete runs and excessive frame gaps.

## Reproduction

1. Copy `tools/solidcraft-worker-probe` into `apps/bigbrain-worker-probe` inside an
   isolated checkout of commit `ee6b85605a32948bcbd9ae437a564cab826689ec`.
2. Build for `wasm32-unknown-unknown` and generate web bindings with the matching
   wasm-bindgen CLI. Preserve the installed source and runtime.
3. Run `tools/serve_cad_worker_qualification.py` with explicit runtime, fixture
   and evidence directories. Launch the campaign from its page.
4. Reopen `saved.sc` using the installed native CLI into `native-reopened.json`.
5. Run `tools/check_cad_worker_qualification.py` with the evidence directory and
   the retained native inspection reference.

Local evidence: `/tmp/cad-worker-evidence-Yez2IJ/`.
Isolated source: `/mnt/cold-hdd/bigbrain-local/solidcraft-worker-028/`.
Runtime: `/mnt/cold-hdd/bigbrain-local/solidcraft-worker-028-runtime/`.
The native installation and BigBrain's configured browser build remain unchanged.

## Integration boundary

The next implementation must keep one authoritative geometry session per
document, match worker/view evaluation identities, retain the accepted checkpoint
until the next operation succeeds, and route hosted editing through the same
execution boundary. Qualified cached geometry must reach the viewer without a
second full timeline evaluation. Worker termination must retain the preceding
accepted checkpoint and fence late results.

Linux and Windows share the Worker protocol. Browser/device support and native
platform checks require separate qualification. Moving synchronous work into
the Worker establishes the execution boundary; production ownership, cancellation
and editor integration still require implementation and tests.

## Handoff

The current branch records qualification and the workspace presentation changes.
Worker-to-Atelier integration is deferred until the next explicit implementation
request. The configured engine remains unchanged in the meantime. Pending work
also includes unified hosted recovery and compact construction observations.
