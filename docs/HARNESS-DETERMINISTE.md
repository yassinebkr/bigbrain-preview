# Deterministic harness — fpga → bigbrain porting plan

Exploration of `../fpga/backend` (Oct 25–26, 2026) and the implementation
plan. Agreed protocol: this document first, the code afterwards.
The French original lives at [fr/HARNESS-DETERMINISTE.md](fr/HARNESS-DETERMINISTE.md).

## 1. Why

Today the PythonBrain announces "hello.py created, it prints Hello,
World!" on the strength of its own run. Nothing proves the claim: no
auditable record, no systematic verification before marking a subtask
complete, no way to replay. The fpga backend solved exactly this
problem for hardware — we port the same ideas for Python.

Guiding principles (borrowed from fpga):
- **The chat is not a source of truth.** Every run leaves a versioned
  `RunManifest`, immutable once completed.
- **An absent or inconclusive tool is never a pass.** (Verilator →
  here: pytest absent = `inconclusive`, not `passed`.)
- **The gate is conservative**: a failed OR inconclusive mandatory
  stage never allows "task complete".
- **Policy and execution are separate**: describing the rules (what
  to verify) is distinct from executing them (how).

## 2. What exists on the fpga side (sources)

| File | LOC | Idea to port |
|---|---|---|
| `evidence.py` | 1,219 | `DesignSpec` (what was asked, independent of the code), `StageResult`, `RunManifest` (exact inputs, tools, stages, metrics, sha256-hashed artifacts), `EvidenceReport` (derived, human-facing), `EvidenceRepository` (durable storage, immutability of completed runs, content-addressed artifacts) |
| `verification_pipeline.py` | 851 | Orchestration as adapters: the pipeline owns the order, the gate semantics, the evidence and the lifecycle; the engines are interchangeable sync/async adapters |
| `verification_policy.py` | 660 | Declared rules/assertions/waivers, independent of execution |
| `verification_executor.py` | 554 | Concrete execution adapters; raw output kept as an artifact; missing tool = `inconclusive` |
| `golden_models.py` | 332 | Reference corpus independent of the generated code |
| `differential_regression.py` | 557 | Differential corpus ↔ generated code; a run is a durable job (survives a WS disconnect), log and manifest persisted |
| `jobs.py` | 738 | Jobs with cancellation, timeout, output streaming |

## 3. What exists on the bigbrain side (starting point)

- `verification/pipeline.py`: V1–V5 levels, V4+V1 active (Lightning).
- `verification/v4_deterministic.py` (~330 LOC): `DeterministicValidator`
  — syntax, result structure, optional mypy/pytest. Superficial: no
  evidence, no artifacts, no manifest, results not correlated with the
  run that produced them.
- `brains/python_brain.py`: the Honk inner loop already exists
  (`_generate_and_execute`: generate → execute → retry with error
  feedback to the LLM, MAX_RETRIES=5). This is the natural anchor
  point: the deterministic gate plugs in there, it does not replace
  the loop.
- `llm/usage.py`: token accounting — to be referenced in the manifest
  (cost per run), not duplicated.

## 4. Target architecture

```
bigbrain/verification/
  evidence.py      ← adapted port of fpga/evidence.py (no constraints/
                     FPGA: simplified DesignSpec = user_request + textual
                     contracts; artifacts = code, stdout, results)
  executors.py     ← deterministic Python stages:
                       1. syntax      : ast.parse (always, free)
                       2. compile     : py_compile
                       3. run         : bounded execution (timeout), captured
                       4. tests       : pytest if test files present,
                                        otherwise inconclusive (not skip-pass)
                       5. contracts   : the requested file exists in the
                                        right place (e.g. "hello.py" in the
                                        project) — the "script created
                                        under another name" bug can no
                                        longer pass
  gate.py          ← conservative semantics: failed/inconclusive on a
                     mandatory stage → subtask FAILED with details,
                     the Honk loop re-prompts the LLM with the error
data/evidence/
  runs/<run_id>/manifest.json     ← immutable after completion
  runs/<run_id>/artifacts/<sha>   ← code, stdout, stderr, tests
```

Integration:
- `python_brain._generate_and_execute` and `_run_existing_file` call
  `gate.verify_run(...)` after each execution; the manifest captures
  every attempt (1..N) with its artifacts.
- `orchestrator`: `subtask.complete` is emitted only if the gate is
  green (the brain already surfaces it via success — make it explicit
  in the payload: `verification: {stages, verdict}`).
- WS/web: `verification.run_recorded` event → the RunPanel displays
  the per-stage verdict (fpga agent-console style pills — UI backlog).

## 5. Phases

### P1 — Evidence core (without touching the existing flow) — DONE
- Port of `evidence.py`: `DesignSpec` (user_request + contracts, semantic
  hash), `StageResult` (statuses where `inconclusive` = terminal),
  `RunManifest` (conservative derived verdict: the worst mandatory
  result wins; cross-validated artifact references), `EvidenceRepository`
  (canonical JSON, atomic fsync writes, sha256-deduplicated artifacts,
  terminal-run immutability, overridable `BIGBRAIN_EVIDENCE_ROOT`).
- Retained layout: `data/evidence/{specs,runs,artifacts/sha256}` (flat,
  global content-addressed artifacts — dedup across runs).
- Tests: `tests/test_evidence.py` (24) — roundtrip, immutability (same
  run_id), conservative verdict, deduplication, traversal refused.

### P2 — Deterministic stages + gate — DONE
- `executors.py`: stage_syntax (ast.parse), stage_compile (compile),
  stage_run (verdict ON the execution already done — the gate never
  replays the code), stage_tests (pytest if test files present;
  absent = not_applicable, missing pytest = inconclusive),
  stage_contracts (the file named in the request exists in the right
  place — catches "hello.py created under another name").
- `gate.py`: RunGate.evaluate_attempt — spec + sha256 artifacts
  (code, stdout, stderr, test output) + immutable terminal manifest,
  attempt chaining via parent_run_id, conservative verdict.
- Wired into the Honk loop (`_generate_and_execute`) and
  `_run_existing_file`: failed verdict → feedback to the LLM (retry),
  inconclusive → no retry (the environment is not fixable by the LLM)
  but never claimed "verified"; the gate NEVER breaks generation
  (internal error → verdict None, legacy behavior).
- Kill switch: BIGBRAIN_EVIDENCE=0.
- Tests: `tests/test_harness_gate.py` (24) — unit stages, end-to-end
  gate, attempt chaining, Honk integration (success, broken→fixed,
  run_file).

### P3 — Replay & differential (golden models pattern) — DONE
- `replay.py`: `replay_run(run_id)` reloads the code from the
  manifest's artifacts, re-executes it in a CLEAN subprocess
  (`run_code`: minimal env, stdin /dev/null, scratch dir), compares
  stdout/stderr/exit against the recorded artifacts → report
  {deterministic, mismatches}. The replay is itself persisted as a
  chained manifest (parent_run_id, metadata.replay_of) with a
  `replay_compare` stage. Only terminal runs are replayable; replaying
  a replay chains the history.
- `golden.py`: reference corpus (hello, fibonacci, file_io, unicode)
  independent of any LLM, executed through the same run_code —
  regression test of the execution machinery (env, encoding, timeouts,
  stdin). `run_corpus()` for tests and a future scheduled job.
- Tests: `tests/test_harness_replay.py` (9) — deterministic replay,
  non-determinism detected (time.time), non-terminal runs refused,
  chaining, full corpus, stdin EOF, infinite loop bounded.
- *Done criterion reached:* a replayed run produces a manifest vs
  replay diff.

### P4 — UI surface — DONE
- PythonBrain broadcasts `verification.run_recorded` on the bus
  (target morphable_ui) after each gate evaluation: {run_id, verdict,
  attempt, stages[{name,status}]}. Best effort — never breaks the run.
- Store: `applyRunEvent` attaches the verdict to the active run
  (orphan events dropped, unknown verdicts → inconclusive, defective
  shapes survive); persisted with activeRun.
- RunPanel: collapsed row → verdict chip (verified / gate failed /
  unverified + "· try N"); expanded → per-stage pills in the
  agent-console style (colored dot: passed green, failed/inconclusive
  orange, not_applicable muted). BrainsView: the verdict enters the
  feed.
- Tests: +1 backend (bus broadcast), +3 vitest (attach, orphan,
  degradation).

## 6. Non-goals (P1–P3)

- No OS sandbox (V2) — out of scope, as in preview.
- No cross LLM review (V3) — already covered elsewhere.
- No full port of `jobs.py`: the PythonBrain's existing bounded
  execution is enough; P3 replay reuses the same path.
- No FPGA/EDA tooling: patterns only, zero fpga imports.

## 8. Possible follow-up (post P1-P4)

- **Contracts proposed for approval before implementation**
  (shopifast-local pattern): today the contracts are auto-extracted
  from the message (named file) and verified AFTER the fact. The
  evolution: the front brain proposes the contract(s) derived from the
  request ("hello.py will be created in project X, it will print
  Hello, World!", tests included), the UI (gen-ui / Phase B morphable)
  displays them clearly and the user approves or edits BEFORE the Honk
  loop starts — the validated DesignSpec becomes the run's spec_sha256
  (the approval is traced in the evidence). Reuses the V5 human-gate
  mechanism on the orchestration side.
- Read-only Evidence API (`/api/evidence/runs`, `/run/{id}`,
  `/artifact?sha`) — current surface: the Evidence section of the
  Brains tab (contracts, stages, verdicts).

## 7. Risks / points of attention

- **Do not break the Honk loop**: the gate enriches the feedback
  (precise deterministic errors), it does not add a second retry loop.
- **Zero cost**: stages 1–2 are free; 3 reuses the execution already
  done (no double run — the manifest captures the Honk run, it does
  not replay it).
- **Manifest path**: `data/evidence/` is already ignored (runtime),
  nothing to re-track.
