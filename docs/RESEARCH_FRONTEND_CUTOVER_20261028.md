# Direct research frontend cutover — 28 October 2026

## Failure and implementation boundary

The reported PostgreSQL `InspectionBudgetExceeded` came from the previous staged
workflow. The experimental direct engine had been validated through an isolated
native harness; the production worker still selected the staged workflow.

The worker now defaults to the direct engine for its model-driven documentary
path. An explicit `research_workflow="staged"` retains the previous path for its
regression coverage. Custom policies and explicitly supplied reviewers preserve
their existing behavior. The shared runtime initializes immutable questions,
restores conversation-owned checkpoints, handles Stop and emits terminal progress
around either workflow.

## Contracts exercised by the frontend investigation

* The frontend accepts direct failure/clarification outcomes and structured
  diagnostics. Direct decision and synthesis phases have user-facing labels.
* Monitored admission is exposed through the existing `stage_budget` view.
* Citation receipt hashes are bound by the runtime to generation-packet passage
  handles. Source assessments choose one observed provenance handle, which binds
  source ownership and literal provenance. The existing citation and source-policy
  validation remains in place.
* Empty optional focus values become unfocused reads. Nonempty literal selectors
  retain their validation constraints.
* Bounded-coverage acquisition retains complete short references and fills the
  available section allowance. Small navigation labels receive less weight in
  the direct working set. Each read source receives a provenance candidate.
* `reading_question` lets the model express retrieval intent in the source
  language. The original user questions remain the acceptance scope. The intent
  guides both acquisition and working-set ranking.
* Repeated consultations keep separate passage identities and stored history.
  Equivalent captured text is deduplicated in the working set. Persistent native
  conversations receive changed observations and short alias references; exposed
  handles remain available while their source captures are current.
* System shutdown drains the process-owned Codex transport while asyncio remains
  available. Subsequent observed server shutdowns completed cleanly.
* Archived captures with verified bodies and hashes survive continuation beyond
  the previous five-minute freshness window. Their original observation dates
  remain visible. Explicit freshness limits and invalid capture checks still
  apply; legacy unsealed evidence retains its expiry.
* Native decision submission briefly drains the asynchronous usage notification
  before interrupting a turn. Missing usage still receives a conservative
  reservation. A delayed-notification regression covers this ordering.
* Documentary partial results use an incomplete status in the chat and Atelier.
  Technical failures keep their failure status. Continuation packets carry the
  original scope, remaining requirements and bounded prior findings.
* Explicit semantic uncertainty survives deterministic source/citation checks.
  A partial candidate receives at most one targeted complement when its decision
  and final synthesis both fit the current allowance. Repeated gaps settle;
  the attempt ceilings and finish reserve remain unchanged.

## Production profile

Default direct limits are 128,000 monitored input units, 8,000 output units, seven
model calls, six HTTP acquisitions, three searches and 120 seconds. The final
synthesis time reserve remains 20 seconds. Existing input-limit overrides are
honored; `BIGBRAIN_RESEARCH_OUTPUT_UNITS` configures the output threshold.
Unknown native usage consumes conservative reservations. An admitted call can
exceed a monitored threshold; following calls are then stopped. These accounting
units can combine measured tokens and reserved estimates. Monetary cost and total
subscription consumption require complete native usage records.

## Verification checkpoint

The backend suite after the complement correction passed: 1,894 tests, eight
skipped, nine warnings (202.45 seconds). The journey module then passed all 17
tests including an additional finish-reserve regression. New coverage includes
the authenticated worker and continuation,
terminal UI diagnostics, shutdown, source-owned provenance, empty focus, the
captured PostgreSQL passages, cross-language qualifications, persistent-context
updates and consultation aliases. Frontend: 137 tests passed and build completed.

Earlier frontend attempts are retained as failures or partial outcomes. They
exposed navigation-heavy selection, copied receipt errors, empty selectors,
cross-source provenance and insufficient coverage under conservative admission.
The frontend wave goes through the real browser, front brain, authenticated bus,
researcher and Atelier. Git and Python completed with four and three findings,
respectively. A literal-anchor audit verified six Git quotation anchors and four
Python anchors, their capture hashes and source ownership. Python explicitly
distinguishes FileNotFoundError from other errors and dates missing_ok to 3.8.

The preceding PostgreSQL continuation remained partial: transaction rollback and
DELETE/DROP identity effects were unresolved. Its checkpoint contained four valid
quotation anchors, but earlier expiry had removed some prior observations. That
attempt exceeded the monitored input threshold during an admitted call and then
settled.

The fresh v11 PostgreSQL attempt read three sources and settled partial in 27
seconds. Its v12 continuation automatically replaced the active Atelier work,
preserved the original research identity and consulted the transaction tutorial
and sequence-function reference. It settled partial in 25 seconds, with five read
sources, four findings and three model calls. Accounting records 110,104 input
units and 2,913 output units, including one unknown-usage reservation; 88,687
tokens were reported by the transport. These figures describe the continuation,
rather than a fresh isolated research cost.

The audit verified nine quotation anchors and five source-ownership judgments in
that continuation. Manual semantic inspection still rejects full acceptance:
the TRUNCATE finding claims row deletion/locking while its own limitations say
those statements lack a retained literal citation. Transaction coverage for
DELETE/DROP and identity effects also remain incomplete. Literal anchor validity
therefore establishes traceability alone. The current remaining problem concerns
selection and synthesis of available evidence. Further technical-failure fixes
or a successful unrelated query cannot close PostgreSQL acceptance.

The latest partial candidate had insufficient forecast allowance for an ordinary
complement plus final synthesis; it retained its partial outcome. The automatic
complement and its budget refusal have offline regression coverage. Full live
coverage remains open. No additional paid attempt is implied by this checkpoint.

Evidence root:
`/home/kwestog/Documents/code/tests/research-efficiency-evidence/frontend-direct-20261028-v12/`.
`source-sha256.txt` identifies the frozen implementation. Browser screenshots,
conversation-owned checkpoints and their citation audits form the acceptance
evidence. Git was exercised on v10, Python on v11, and the PostgreSQL continuation
on v12; copied checkpoints preserve their actual attempt identities. The source
hashes in the v12 directory identify the latest implementation. Earlier runtime
snapshots remain in their respective evidence directories. The historical
isolated five-probe campaign retains its earlier scope
and limits in `RESEARCH_DIRECT_FIVE_PROBES_20261027.md`.
