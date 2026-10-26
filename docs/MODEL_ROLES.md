# Front and research provider assignments

On 25 October 2026 the requested local configuration is:

| Role | Registry key | Model | Effort | Transport |
| --- | --- | --- | --- | --- |
| Front brain | `codex-sol-6.1` | `gpt-6.1-sol` | `low` | Codex subscription |
| Web research, including evidence assessment | `codex-luna-6` | `gpt-6-luna` | `low` | Codex subscription |

Assignments are stored in ignored local `data/model_roles.json`. Existing planner,
code, web-app and subagent entries were retained. No API credentials were changed.
The existing generic `codex-chatgpt` entry remains backward compatible.

## Actual execution, not only display

Previously `model_roles` persisted display choices, while system construction and
provider reload handed the global provider to both front and research. This could
show Sol in the UI while Mistral Studio high executed the request.

`BigBrainSystem._provider_for_role` now builds and caches the explicitly assigned
front and research providers independently. The startup paths, researcher plugin
re-enable path and global credential/provider reload preserve this separation.
The model-role HTTP endpoint applies these two roles to the runtime holders.
Unassigned roles keep the legacy provider fallback; this change does not claim
complete per-role provider routing for planner/code/web-app/subagent.

The two named Codex entries use their registry effort rather than inheriting the
legacy global `BIGBRAIN_CODEX_EFFORT`. Per-key environment overrides still exist.
The effective model/effort are recorded in inference traces and pending-front
status events. No inference was needed to inspect the constructed providers.

## Verification

96 focused Python tests passed, including independent provider instances, global
reload isolation, role endpoint runtime application and legacy model compatibility.
130 UI tests and production build passed. All tests isolate the model roles file
under their temporary roots. The user's model selections were changed only after
these focused checks, preserving other entries.

Restart the running server and reload the browser to load this implementation
and the persisted assignments. A running pre-change process is not automatically
modified by editing files. No new paid inference, commit, push or merge here.
