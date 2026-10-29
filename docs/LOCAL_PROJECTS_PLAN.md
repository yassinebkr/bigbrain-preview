# Attached local projects: approved contracts and implementation plan

29 October 2026. The six contracts below are approved. The phased implementation
plan is approved for implementation. Branch: `feat/local-projects`.

## Implementation status

| Phase | Evidence | Remaining work |
| --- | --- | --- |
| 1 | Access inventory and boundary specification in `LOCAL_PROJECTS_BOUNDARIES.md`; local bwrap smoke check | Trace individual integration callers |
| 2 | Registry, filtered listings, descriptor-scoped reads and local HTTP chooser tickets; 14 regression cases pass | Production UI journey and caller integration |
| 3 | Real snapshot subprocess and revocation tests pass; scoped Python run endpoint | Project interpreter, transaction publication and repair integration |
| 4 | Existing project selector identified | Trusted chooser and attachment journeys |
| 5 | Acceptance matrix recorded | Cross-path campaign and runtime acceptance |

Overlapping attachments are rejected while an overlapping root remains attached.
The native chooser currently uses Zenity and requires a local desktop session.
HTTP access requires a loopback client, an approved Host, a matching Origin and
the local UI request header. Selection tickets expire after two minutes.

The initial file replacement primitive checks the observed input hash. External
edits during replacement and directory relocation require stronger publication
protection before attached-project writes become available through production
routes.

Snapshot execution currently supports Python standard-library commands with the
BigBrain base interpreter. Bubblewrap exposes the copied source tree, runtime
libraries and private temporary storage. Execution has a time limit and a bounded
output buffer. The host source tree stays outside the process namespace. Two
real execution tests cover outside-root access, scratch writes and revocation.
Project-specific environments, package installation and web preview integration
remain acceptance work for Phase 3.

## Approved contracts

1. Persist project identity, canonical root and explicit read-only/read-write
   grant. Conversations reference the project independently of its lifecycle.
2. A trusted local chooser authorizes roots. Model-proposed paths cannot grant
   access. Relevant brains enforce the same grant at every tool boundary.
3. Resolve symlinks and refuse root escapes. Define exclusions for credentials,
   hidden files and generated folders. Attachment grants no blanket indexing,
   embedding or transmission to providers.
4. Preserve user changes, version patch inputs and detect concurrent edits.
   Inspect actual manifests and entry points with provenance.
5. Separate access from execution, deletion, package-installation and network
   permissions. Define revocation during active work and after restart.
6. Separate scratch/preview artifacts from sources. Show path and rights. Test
   unavailable drives, renames, overlapping roots, concurrent edits, symlink
   escapes, revocation and restoration. Detachment preserves user files.

## Scope

Implement one shared project/access foundation for existing local folders.
Integrate it with current code workflows and existing sandbox projects. A CAD
adapter and its revision-bound preview follow after this foundation is accepted.
Shared-focus architecture, photo reconstruction and printer control are deferred.

## Phase 1 — Architecture boundary and frozen acceptance

Map current project selection, global filesystem roots, memory references,
maintenance transactions, runner subprocesses and frontend selection. Identify
every access path that could bypass a grant, including indirect subprocess access.
Reuse existing components where their behavior meets the approved contract.

Specify project/grant identities and versions, API/storage migration, trusted
chooser, local-request authentication/origin protection, attachment and revocation
states, provider-transmission consent and excluded paths. A browser directory
upload alone cannot supply an authoritative server-local filesystem grant.
Explain any guarantee that needs process isolation or an additional user choice.

Freeze acceptance cases before implementation. Escalate unresolved material
tradeoffs instead of choosing weaker enforcement implicitly.

**M1:** reviewed design, complete tool-access inventory and fixed acceptance
matrix. Every promised restriction maps to an enforceable boundary.

## Phase 2 — Registry and filesystem capabilities

Implement persistent attached/sandbox project references and scoped grants.
Centralize canonicalization, root containment and exclusions. Provide narrowly
scoped reads/listings/writes; implement read-only, revoked and unavailable states.
Prevent string-prefix and symlink escapes, including changes during operations.
Retain project identity across conversations and restart.

**M2:** offline fixtures pass containment, read-only, exclusion, overlapping-root,
stale-grant and restart tests. User folders remain unchanged during attach/detach.

## Phase 3 — Safe modification and execution boundaries

Bind maintenance reads/patches to project and grant revisions. Reuse hash and
transaction protections; reject concurrent changes and verify recovery. Grant
execution/install/delete/network independently and enforce access for runners
and other subprocesses. Scope preview and scratch artifacts to their project.
Revocation blocks subsequent operations and has explicit running-action behavior.

**M3:** an authorized synthetic project can be repaired and verified; read-only,
concurrently edited and revoked variants fail safely with useful diagnostics.
Subprocess restrictions match documented guarantees.

## Phase 4 — User-facing attachment and continuity

Add a trusted local-folder selection flow, explicit access confirmation and clear
path/rights display in the existing project UI. Show unavailable/conflict/revoked
states, support detach, and keep conversation selection separate from attachment.
Preserve selection through navigation and refresh without leaking another
project's state. Explain separately any requested execution or transmission grant.

**M4:** real UI journeys cover attach, select, read-only, write grant, navigation,
restart, conflict and detach. All displayed files and states come from runtime.

## Phase 5 — Cross-path hardening and acceptance

Run the fixed matrix across API, tools, runners and frontend. Include malformed
requests, path encodings, secrets, symlink swaps, unavailable drives, renamed roots,
overlapping attachments, concurrent runs, revocation and recovery after failure.
Use disposable Python and web fixtures; verify that unrelated folders stay intact.
Run backend/frontend suites and build. Model-led probes require scoped consent
for source transmission and cost; avoid transmitting personal folders implicitly.

**M5:** acceptance report maps all six contracts to concrete evidence, records
limitations and leaves no silent access bypass. Merge awaits user authorization.

## Following milestone — CAD brain and piece preview

Close the CAD artifact/preview contract, then implement a dedicated SolidCraft
adapter using the shared access foundation. Keep headless computation, native
history and geometry checks, fast previews, and optional GUI handoff. Show the
piece as a compact expandable object in the principal work surface. Every view
binds to a project/document/revision and exposes stale or failed updates.

Qualification starts with the dimensioned plate, enclosure, parameter edit and
rollback cases already exercised against the local engine. Autonomous modeling
and interactive preview acceptance remain separate from engine qualification.
Photos/diagrams remain a later stage with explicit scale and uncertainty.

See [SolidCraft qualification](SOLIDCRAFT_QUALIFICATION_20261029.md).
