# Research implementation checkpoint — 26 October 2026

Branch: `feat/front-decision-v1`. Purpose: preserve completed implementation and
document open gates before the next architecture decision. Merge remains pending
explicit user authorization.

## Included work

- Native front decisions, validated delegation and bounded terminal responses.
- Independent front/research model roles and Codex action transport with call
  traces, explicit unknown usage and conversation-scoped research bindings.
- Complementary grouped reads, observed section selectors, fresh-cache reuse,
  acquisition quotas and capture-bound references.
- Focus/definition extraction and compact source-balanced policy contexts.
- Fixed delegated obligations and generation-time action variants, followed by
  runtime validation and bounded diagnostic feedback.
- Documentary findings and source links preserved through chat delivery, with
  partial findings, checkpoints and updated Atelier presentation.
- Review evidence assembly and current strict question/claim ownership checks.

## Validation status

An earlier full backend run passed 1,667 tests with eight skips. Later changes
followed, so that result describes its retained source revision. The most recent
focused review/context run before this checkpoint passed 107 tests and failed
`test_long_review_is_bounded_and_restores_uncited_counterevidence`.

Current pre-push validation on the checkpoint sources:

- Backend: 1,696 passed, eight skipped, nine warnings, one failure in 187.56 s.
  The failure is the repeated-prose original-section restoration test named above.
- Frontend: 133 tests passed; TypeScript and production build passed. The existing
  bundle-size warning remains visible.
- Staged whitespace validation passed. Local `AGENTS.md`, user memory and
  `uv.lock` are excluded. A targeted added-line credential-pattern scan found no
  matches; this is a limited check, rather than a repository-wide security audit.
- The first backend attempt stalled in the restricted execution environment and
  was interrupted. One bounded host rerun produced the result above. The initial
  UI build hit read-only temporary-file writes; the host rerun passed.

Logs are retained in the adjacent local tests workspace under
`research-efficiency-evidence/prepush-backend-host-20261026.log`,
`prepush-ui-20261026.log` and `prepush-ui-build-20261026.log`.
These local results are separate from GitHub CI on the pushed commit. The current
workflow runs on main pushes and pull requests; this branch push alone does not
establish a CI outcome. No merge or new live model call belongs to this checkpoint.

## Known unresolved issues

1. Review restoration uses text containment to map consulted passages to original
   sections. Repeated prose can select unrelated sections and exceed the bounded
   inspection envelope. Exact block/range identity is required.
2. Successful Git and SQLite journeys coexist with partial repetitions. Scope
   interpretation, qualification retention and sufficiency judgments vary. A
   successful individual run does not establish general reliability.
3. Collection and review independently construct their evidence contexts. This
   can omit a consulted qualification from the final inspection packet.
4. Native history and missing usage reports limit context/cost accounting. The
   planned API-equivalent estimate requires verified official pricing and an
   explicit mapping from aliases to public model IDs.
5. Strict assessment rejected a retained report that assigned one question's
   claim to another. The ownership guard remains active. No rejected ownership
   relaxation belongs to this checkpoint.

The earlier browser report in the adjacent local tests workspace,
`research-efficiency-evidence/END_TO_END_20261026.md`, covers part of the campaign.
Subsequent retained runs include successful and partial journeys, schema failures
and a frozen Sol review rejected by strict assessment. Many interrupted native
turns have unknown usage. No aggregate claim of measured consumption is supported.

## Next decision

[RESEARCH_CLOSURE_PLAN.md](RESEARCH_CLOSURE_PLAN.md) proposes explicit stages,
a shared immutable dossier, separate Luna control and one targeted recovery cycle.
It also sets proposed resource ceilings, acceptance criteria and campaign stop
conditions. Architecture implementation and new live runs await authorization.
No new scraper, model escalation, provider fallback or UI redesign is included.
