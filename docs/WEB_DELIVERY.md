# Static web delivery

`WebAppBrain` generates HTML/CSS/JavaScript and validates local artifacts
before returning an executable project and preview URL. `index.html` must
exist, contain a semantic `main` region and reference existing local files.

The architect and worker share the acceptance protocol in
`bigbrain/brains/web_acceptance.py`. New `tests/acceptance.json` files are
validated and saved in this canonical form before `workspace.file_written`:

```json
{
  "schema_version": 1,
  "cases": [{
    "name": "Open the application",
    "steps": ["Open index.html"],
    "assertions": ["The requested application is visible"]
  }]
}
```

`cases` and `assertions` must be non-empty arrays; `steps` is optional.
Items may be non-empty strings or objects. Unsupported versions and malformed
documents fail explicitly. Pre-v1 `cases`, `tests` and `acceptanceCriteria`
documents are adapted at the boundary, including `title`, `expectedResults`
and step-based scenarios. The original user project is not rewritten by the
read-only validator.

These documents describe acceptance scenarios. The static gate does **not**
execute browser assertions. Its evidence explicitly records
`scope=static_artifacts` and `browser_tests_executed=false`. A runnable preview
does not mean all interactions have passed browser tests.

A worker returning `success=false` must retain that status in the bus result
envelope. The orchestrator then emits `task.failed` with the actual cause and
`runnable=false`. A failed run cannot inherit the launch metadata of the
previously selected project. The front brain reports the failure without an
LLM summary, and the docked card displays the cause even when collapsed.

Successful assembly emits `task.complete` with `project_path`, `entry_point`,
`deliverable_type`, `runnable` and the real `preview_url`. The docked React
card keeps its iframe and Open/Run controls visible. Regression coverage:
`tests/test_web_delivery.py` exercises the real bus and preview HTTP server;
`RunTimelineCard.test.tsx` checks the collapsed render.
