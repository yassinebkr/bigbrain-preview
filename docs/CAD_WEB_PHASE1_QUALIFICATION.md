# SolidCraft 0.28.0 browser qualification

## Outcome

The browser round trip passes on the retained plate and drawing 42 revision 14.
Named feature history, parameters, valid feature states, closed bodies,
undo/redo and native reopening pass the recorded comparisons. Independent STEP
volume and bounding-box comparisons pass through BigBrain's existing OpenCascade
measurement provider.

Integration readiness remains limited by synchronous geometry work and incomplete
WebGPU qualification. Drawing 42 blocks the browser event loop for approximately
36 seconds during loading and parameter reconstruction. The observed rendering
backend is GPU-accelerated WebGL/ANGLE, including when `&webgpu` is requested.
This environment therefore establishes WebGL behavior; actual WebGPU execution
requires a compatible browser configuration and a separate observed run.

## Build identity

| Field | Value |
| --- | --- |
| Source tag | v0.28.0 |
| Source commit | ee6b85605a32948bcbd9ae437a564cab826689ec |
| Source modifications | Pristine tag archive |
| Rust | 1.99.1 (58cf8f9c3, 2026-10-13) |
| Trunk | 0.22.1 |
| Trunk archive SHA-256 | 2ab8d548fd5ed9cda50906f61fd8654204e7893bd52ebbfd90533862b7d71ee1 |
| Build | `trunk build --release --public-url ./ --locked` |
| Offline asset identity | 0.28.0-47a2da7690abce26 |
| Platform observed | Linux, Chromium 155, RTX 3070 Ti |

The distribution and compilation cache are under
`/mnt/cold-hdd/bigbrain-local/solidcraft-web-028/`. The site is
`source/dist/web/`; `qualification/build-identity.json` records every asset hash
and fixture identity. The distribution occupies approximately 99 MiB, including
a roughly 93 MiB WebAssembly module. These local loading measurements do not
estimate an internet download on a user's connection.

The isolated native helix patch is excluded from this baseline. Its native
qualification remains separate. A patched web build must receive its own build
identity and helix comparison before replacing this baseline.

## Observed cases

| Check | Plate | Drawing 42 |
| --- | --- | --- |
| Native source opens in browser | Passed | Passed |
| Named history and parameter inventory | Passed, 3 features | Passed, 29 features |
| Sketch names, curve/profile counts and solver states | Preserved | Preserved, 11 solved sketches with zero DOF |
| Parameter reconstruction | width: 60 to 61 mm | flange_thickness: 50 to 51 mm |
| Feature errors and closed body inventory after edit | Passed | Passed |
| Undo restores original geometry | Passed | Passed |
| Redo restores edited geometry | Passed | Passed |
| Save and reopen in browser | Passed | Passed |
| Browser native file reopens in original native engine | Passed | Passed |
| Independent STEP volume and bounds | Passed | Passed |

Native comparisons use body names, closure, volume (relative tolerance 1e-7) and
bounds (0.001 mm). Independent STEP comparisons validate the boundary
representation, solid inventory, surface-integrated volume (relative comparison
tolerance 1e-5) and bounds (0.001 mm). This phase compares round-trip geometry;
it does not repeat the entire original drawing 42 delivery procedure or certify
manufacturing tolerances. Original source artifacts remain unchanged.

## Timing and memory

| Operation | Plate | Drawing 42 |
| --- | ---: | ---: |
| Open source, observed local run | 1.418 s | 36.547 s |
| Parameter edit | 0.032 s | 35.727 s |
| Measured inspection after edit | 0.087 s | 5.223 s |
| Undo / redo | 0.008 / 0.005 s | 0.013 / 0.013 s |
| Save native file | 0.102 s | 0.084 s |
| Export STEP | 0.039 s | 0.901 s |
| Reopen saved file | 0.524 s | 35.975 s |

An earlier first plate load took 2.316 s. Runs share browser and filesystem
caches; these are observed local timings rather than a cold/warm performance
distribution. The drawing 42 run records a 36.048 s maximum parent animation-frame
gap. Commands execute on the application's UI thread in the pinned implementation.
Animation alone cannot preserve responsiveness during these synchronous blocks.

The explicit WebGL plate run passes the same round-trip comparisons. It reports
`gpu` rendering through `Gl / ANGLE / RTX 3070 Ti` and a sampled peak WebAssembly
linear memory allocation of 51,773,440 bytes. A separate drawing 42 load with
`&webgpu` still reports the GL adapter and 601,554,944 bytes of WebAssembly linear
memory (approximately 574 MiB). This is a loaded-document allocation, rather than
the peak during all edits. JavaScript heap samples are retained separately.
GPU memory and complete per-tab resident memory were not measured.

## Evidence and reproduction

`tools/serve_solidcraft_web_qualification.py` serves a pinned build and disposable
copies of explicitly supplied documents. `tools/solidcraft_web_qualification.js`
drives its actual browser API and captures actual save/export bytes. Browser
actions launch the checks through the fixture's buttons. The comparison tool is
`tools/check_solidcraft_web_qualification.py`.

Persistent evidence directories:

- `qualification/`: primary browser report, native inspections, captured files,
  build identity and per-case qualification results.
- `qualification-webgl/`: explicit fallback plate results and drawing 42 runtime
  measurements, including `drawing42/runtime.json`.

Two qualification-driver issues were isolated and retained: bare file paths
remain in the browser VFS, so download capture requires `/downloads/`; navigation
must wait for the requested document rather than accepting the previous API
instance. Fresh iframe contexts now make reopen checks independent of unsaved
document prompts. Neither issue required a SolidCraft source change.

No model calls were used. The qualification site and instrumentation remain
separate from BigBrain's product interface.

## Next boundary

Before seamless integration, choose and qualify how synchronous engine work is
isolated from BigBrain's responsive UI. Preserve command ordering, history and
checkpoint identity. Qualify actual WebGPU on a supporting browser, and record
Windows coverage separately. The measurements provide the inputs for that
decision; this phase adds no worker or production bridge implementation.
