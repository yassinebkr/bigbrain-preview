# Isolated SolidCraft 0.28.0 helix correction

## Source and purpose

Apply `solidcraft-0.28.0-helix.patch` to the clean upstream commit
`ee6b85605a32948bcbd9ae437a564cab826689ec` (tag `v0.28.0`).
It refines the smooth screw-sweep interpolation: 24 samples per profile segment
and 48 stations per turn. The existing 4,800-station cap remains in force.
An additional kernel regression checks section and angular area independently.
The native feature and document format remain unchanged.

The original coil uses an axial section under screw motion. Its expected volume
is section area times angular travel times centroid radius. Refinement changes
the generated geometry; measured results retain the original acceptance limits.

## Build and qualification

Use an isolated checkout and Rust toolchain satisfying the upstream requirement.
Keep build output outside the BigBrain repository. From the source checkout:

```sh
git apply /path/to/bigbrain/tools/native/solidcraft-0.28.0-helix.patch
cargo test --locked --profile ci -p solidcraft-kernel helix::tests
cargo build --locked --profile ci -p solidcraft-cli --bin solidcraft-cli
```

Select the resulting executable only for the qualification process with
`BIGBRAIN_SOLIDCRAFT_CLI`. Use the platform-specific executable path (`.exe` on
Windows). Run the original coil test and the `precision_matrix` cases in
`tools/cad_coil_diagnostics.py`; retain artifacts on the configured CAD disk.
Record source commit, patch hash, executable hash, platform and test evidence.
Linux results require separate Windows compilation and execution evidence.

## Runtime selection and retirement

The application installation remains unchanged during qualification. Its existing
executable-selection interface keeps the correction outside controller logic.
Retain the original executable and never overwrite saved source models.
Use separate run/checkpoint roots for each executable variant. The current
checkpoint contract records the native version; both binaries report `0.28.0`.
Checkpoints and newly captured revisions now record the executable SHA-256.
Execution and recovery verify it before native document access. A build change
requires a new candidate; legacy records remain viewable and require a fresh
candidate for execution. Hashing uses the shared Python adapter on both platforms;
native Windows qualification remains pending.

The isolated correction covers the headless executable. The existing desktop
installation retains the original kernel; editing helical features there requires
its own corrected-build qualification. Preserve independently verified revisions
when handing a model to that desktop installation.

This patch qualifies the explicitly measured configurations. Long sweeps reach
the station cap, and interpolation cost increases with station count. Full native
CI, complete drawing 90 qualification and high-turn accuracy/performance remain
separate checks. The patch introduces no faceted backend substitution.

When an upstream release addresses this precision defect, replay the original
failing test, the precision matrix, parameter edits and saved-model reopening.
Use the upstream native operation once these gates pass and retire the local patch.
