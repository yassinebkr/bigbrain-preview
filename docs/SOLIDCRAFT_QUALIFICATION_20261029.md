# SolidCraft local qualification

29 October 2026. Release: v0.25.1 Linux x86_64, portable archive. The official
checksum matched `5e467b42530808c75e19f4993247d9ab736e700a1532e40eab2bd3da42a2db2f`.
Local user installation, XFCE application entry and executable desktop shortcut
are in place. Launchers use explicit control mode to avoid automatic registration
into other AI-client configurations.

## Comparative audit

The preliminary audit occurred on 19 October. Its exact inspected commit was
unrecorded; v0.16.1 provides a reconstructed stable baseline. Tagged v0.25.1 MCP
source and documentation add typed command inspection, optional strict parameter
checks, detailed restoration/applied-step reporting and parameter coalescing.
Measure distinguishes open surfaces from closed solids. Strict checks are
headless-only and disabled by default.

Release notes describe relevant cut/hole/STEP fixes and performance improvements.
The v0.24.1 cross-component Join regression is fixed in v0.25.1. Both tagged oracle
documents report 83/83 reference cases; these project-reported results were not
rerun. The full comparison API timed out; this audit covers tagged source spot
checks and release notes rather than an exhaustive commit review.

Sources: [old MCP](https://github.com/tangency-labs/solidcraft/blob/v0.16.1/docs/mcp.md),
[new MCP](https://github.com/tangency-labs/solidcraft/blob/v0.25.1/docs/mcp.md),
[tool implementation](https://github.com/tangency-labs/solidcraft/blob/v0.25.1/crates/mcp/src/tools.rs),
[release](https://github.com/tangency-labs/solidcraft/releases/tag/v0.25.1).

## Twelve real local checks

| Check | Observed result |
| --- | --- |
| Two-hole plate | Closed 60 × 40 × 6 mm solid; analytic volume matched |
| Width change | 60 → 80 mm; expected volume and bounds matched |
| Hole topology | Two radius-3 holes retained centers (15,20), (65,20) after edit |
| Execution rollback | Zero-length box failed after an edit; prior measurements restored |
| Strict preflight | Unknown field refused the batch before its first operation |
| STEP round trip | Closed plate reopened with expected volume and bounds |
| Native editability | Reopened design retained its parameter and rebuilt |
| Headless PNG | 960 × 600 GPU image; both holes visually confirmed |
| Enclosure | Closed 60 × 40 × 25 mm solid; 13,632 mm³ matched after STEP reopen |
| GUI live edit | Same document ID advanced revision; geometry matched |
| Native GUI handoff | Headless-created enclosure opened with expected geometry |
| Display-free render | GPU image succeeded with display variables removed |

The persistent eight-case headless sequence took 1.338 seconds after startup.
GUI edit/check sequence: 0.1006 seconds; following render: 0.0277 seconds.
Display-free standalone snapshot: approximately 0.52 seconds including startup.
These single measurements concern small synthetic models on an RTX 3070 Ti.

Authored recipes tested the installed engine. Autonomous LLM design, arbitrary
wall-thickness checks and independent STEP consumers remain unvalidated. The
first harness invocation failed on a helper-name collision before CAD commands;
the corrected harness produced these results. No paid inference or printer call
occurred. Raw transcripts, native files and generated previews remain local.

## Integration boundaries

Headless sessions and the GUI own separate state. Native save/open provides a
tested handoff; connected MCP edits the GUI state. Continuous mirroring and an
interactive BigBrain piece widget remain future work. Pin the release and retain
native files; format 41 requires a compatible application. Keep path grants narrow
and verify actual state before retrying interrupted mutations.

Project-folder contracts and the proposed implementation sequence are recorded
in [the local projects plan](LOCAL_PROJECTS_PLAN.md).
