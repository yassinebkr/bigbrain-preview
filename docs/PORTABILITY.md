# Linux and Windows portability

Architecture rule adopted on 29 October 2026. Existing platform-specific blocks
enter the deferred adaptation backlog below. This decision records architecture
and the remaining adaptation work.

## Rule for all blocks

- Linux and Windows are target platforms for BigBrain and future sub-brains.
- Define shared behavioral contracts and acceptance cases before selecting native
  mechanisms. Platform adapters implement filesystem, execution, desktop and
  tool-integration operations.
- Keep orchestration, permission decisions, repair logic, evidence formats and
  UI state shared. Concentrate native calls behind explicit adapter boundaries.
- Preserve the same safety requirements: version-bound access, source consent,
  conflict detection, recoverable publication, cancellation and bounded execution.
- Report unavailable capabilities with actionable diagnostics. A missing native
  primitive blocks the affected operation; permission checks remain enforced.
- Qualify each adapter on its actual operating system. Record support per
  capability and platform, including environment prerequisites and pending gates.
  Cross-platform support requires Linux and Windows acceptance evidence.

## Current publication design

The shared transaction interface uses native Linux and Windows publication and
retention-release adapters. At `1dbbf86`, fourteen native cases pass on each
platform, including preservation, concurrent changes and exclusive cleanup.

| Scope | Qualification |
| --- | --- |
| Native publication and retained-object release | Linux and Windows CI |
| Shared journal, conflict resolution and production UI | Linux application tests and UI journeys |
| Complete Windows application | Deferred adaptation below |

The [publication design](PUBLICATION_PORTABILITY_DESIGN.md) describes the lifecycle,
storage policy and native mechanisms. The
[acceptance ledger](LOCAL_PROJECTS_ACCEPTANCE.md) records exercised assertions and
remaining limits.

## Deferred adaptation backlog

Initial inventory from the current source tree; extend it during each block audit.

| Block | Current coupling / inspection target | Deferred adaptation and gate |
| --- | --- | --- |
| Registry, research leases and transactions | `local_projects.py`, `research_sessions.py`, `project_transaction.py`: `fcntl` locks | Native lock adapters; multiprocess ownership, contention, cancellation and restart cases on both systems |
| Scoped filesystem access and publication | `project_file_io.py`, `local_projects.py`: POSIX descriptors, `dir_fd`, `O_NOFOLLOW`, inode identity | Native path/handle identity, Windows links/reparse points, case/path rules, durable preservation and shared publication/recovery tests |
| Isolated Python/Node execution | `local_project_runner.py`: Bubblewrap, Unix mounts, process groups, `.venv/bin/python` | Windows execution isolation and project-runtime discovery; outside-root/environment/network denial, Stop, revocation, output limits and orphan cleanup |
| Other subprocess lifecycles | `verification/web_gate.py`, `verification/executors.py`, `brains/web_stack.py` | Audit platform branches, dependency discovery, process-tree termination and browser/runner cleanup; qualify Windows behavior |
| Native folder selection | `web/local_projects_api.py`: Zenity | Windows native picker under the same one-use ticket, origin, expiry and root-identity contract |
| Browser preview and artifacts | `local_project_web.py`, `local_project_preview.py` | Windows Chromium launch, sandbox prerequisites, worker network policy, temporary storage, build artifacts and lease cleanup |
| External tools and CAD | SolidCraft qualification and future adapter | Per-platform installation, executable discovery, headless operation, GUI handoff and revision-bound preview evidence |
| Packaging and installation | Runtime paths, environment setup and desktop launchers | Platform-specific setup/launch instructions and clean-machine installation qualification |
| Continuous integration | `.github/workflows/ci.yml`: Ubuntu jobs | Add Windows jobs and capability-specific native integration gates; keep skipped/unsupported cases explicit |

## Migration milestones

1. Audit platform dependencies and freeze the shared capability/test matrix.
2. Implement common interfaces and qualify Linux/Windows filesystem, lock and
   publication adapters; preserve the existing transaction/evidence engine.
3. Adapt execution isolation, process lifecycles, native selection and previews.
4. Qualify external-tool installation and headless/GUI integration on both systems.
5. Run both-platform CI and clean-install end-to-end acceptance before claiming
   complete Linux/Windows compatibility.

Scheduling of these adaptations remains deferred. The current Linux validation
results retain their original platform scope.
