# Research evidence allocation

Current release decision: [scope and limits](RESEARCH_CLOSURE_20261029.md).
The mechanisms below are implemented; the documentary acceptance gate remains
open and further development awaits user direction.

## Implementation scope

Phase 3 introduces structural evidence allocation in the direct research worker.
The implementation preserves literal focus, source-bound receipts, explicit
character windows, continuation quotations and existing finite call/time limits.
The working-context ceiling remains 12,000 UTF-8 bytes.

`research_allocation.py` supplies structural bundles, independent requirement
queues and round-robin scheduling. Acquisition ranks complete sections using the
existing lexical scores. Decision context scores the strongest substantive block
inside each bundle. Both stages use the same requirement-queue utility with
their respective reading granularity. The experimental embedding model remains
outside the production dependency set.

## Allocation and continuity

- Preserve explicit windows and verified prior evidence first.
- Build contiguous bundles within a source, capture and heading context.
  Split larger sections at original block boundaries with a target of 1,800
  characters; oversized individual blocks remain intact and navigable.
- Maintain a queue for each fixed question and source-bound reading intent.
  Visit one candidate from each queue before spending space on deeper candidates.
- Admit each structural bundle atomically. Keep omitted blocks in the receipt
  archive and expose their catalog when space permits.
- Publish `evidence_allocation`: `candidates_visible`, `no_match` or
  `budget_blocked`. These statuses describe retrieval; semantic coverage remains
  an explicit conclusion judgment. `sibling_context_omitted` identifies additional
  section material outside the visible view.
- Let the existing controller admit targeted expansion while retaining its final
  synthesis reserve. A blocked requirement remains an explicit evidence gap.

Bundle boundaries are structural. An exception elsewhere on the page can remain
unseen. This change supplies a traceable allocation mechanism and retains that
coverage limitation.

## Compact native view

The previous packet budget charged a capture hash and receipt hash on every
passage. The native adapter subsequently removed those fields before generation.
Native packets now omit the repeated hashes from the evidence allowance. The
adapter reconstructs their binding from actual current observations and checks
source ownership, original offsets and literal text before exposing a handle.
The source ledger retains the capture identity. Final citation validation still
uses the controller's immutable receipt archive.

Generic inference adapters retain their full-metadata packet contract. The native
adapter explicitly opts into the compact view. Persistent native aliases and
final evidence snapshots retain their existing behavior.

## Offline evidence

Eleven added tests cover source/capture separation, original-block preservation,
queue interleaving, source-bound intents, atomic admission and budget diagnostics,
unmatched questions, compact binding and four tampered-window variants. The
85-test direct-worker/context/corpus subset passed before the final extraction
granularity preservation. The final-source research/provider gate passed 556
tests with eight skips and 1,364 deselections in 22.53 seconds. The external
measurement harness passed 14 tests and skipped its historical-source replay;
the current-source replay has its own source-hash manifest.
The full backend run passed 1,920 tests with eight skips in 195.16 seconds.
Its source snapshot preceded the last section-granularity preservation; the
556-test gate above verifies that final research/provider adjustment.

The frozen five-case replay remains in the external evaluation workspace:
`/home/kwestog/Documents/code/tests/research-context-evaluation-20261028/phase3-allocation.json`.
It preserves the phase-2 corpus digest and records the final production source
hashes. The historical phase-2 reports remain unchanged; their runner requires
`--current` to write a separate comparison after source changes.

| Case | Phase-2 lexical control | Phase-3 native allocation | Saved checkpoint replay |
| --- | ---: | ---: | ---: |
| Python | 2/5 | 4/5 | 5/5 |
| Git | 4/4 | 3/4 | 4/4 |
| SQLite | 4/5 | 4/5 | 5/5 |
| PostgreSQL | 6/10 | 6/10 | 5/10 |
| Klipper | 3/6 | 3/6 | 6/6 |
| Total | 19/30 | 20/30 | 25/30 |

The automatic control gains one annotated requirement overall and loses Git's
conflict-retention passage. The saved checkpoint replays preserve their aggregate
25/30 visibility, including all annotated requirements in four cases. PostgreSQL
still omits five required passages in that final checkpoint view. Passing runtime
tests therefore leaves the documentary acceptance gate open.

Native compact checkpoint packet sizes: Python 6,240 bytes, Git 9,489, SQLite
11,963, PostgreSQL 11,931 and Klipper 11,191. These compare identical saved evidence
states; they measure context visibility rather than fresh research answers.

## Remaining gate

The allocation mechanism and native binding are implemented. Reliable selection
across the frozen requirements remains open. The Git control regression and
PostgreSQL omissions require an explicit decision before claiming research
acceptance or starting the Phase-4 live campaign. No paid inference, live source
acquisition, frontend validation, commit, push or merge occurred in this phase.

Several recorded research states retain one broad question covering multiple
requested aspects. Source-reading lanes improve diversity within that scope,
but their visibility status cannot establish that each underlying aspect has
been answered. This limits the current allocation guarantee and must be included
in the next decision about a finer evidence-requirement contract.
