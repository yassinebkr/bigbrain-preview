# Web delivery: React/Vite and Chromium

Pre-merge hardening is tracked in [WEB_APP_HARDENING.md](WEB_APP_HARDENING.md).
Web assessment is now preserved through architecture and worker assignment;
invalid planning fails explicitly instead of degrading to Python. The
architect proposes acceptance contracts in its response, avoiding a separate
contract-drafting round trip for projects. Preparation stages carry timings.
Recorded approval is required before execution; an HTTP acknowledgement alone
does not resolve the approval card. Runs/proposals are persisted per conversation;
Stop targets that session and worker events carry plan/session identifiers.
Concurrent front replies retain their own coroutine context. Same-conversation
chat turns are serialized per server, and history defaults to socket scope, not
another tab's last session. Live multi-tab/product campaign work remains open.

## Conversation isolation

Home/New Chat (including keyboard and command-palette navigation) creates a
real session, clears transient text/approval state immediately and waits for
the session id before sending its first message. Late history/session-create
responses cannot replace a conversation opened meanwhile. Finished run cards
keep their original session; foreign chat frames and terminal run events do
not modify the visible conversation/current run. Stop is hidden on Home.

The selected workspace directory is navigation context, not an instruction
to reuse a previous project's name or requirements for a new request. The
front brain is instructed to distinguish edits from a separate new project.

Legacy Python file-generation prompts initialize shared progress/interjection
sections with or without an architect spec. Plans emit a terminal result
only once, even if other workers finish after a fatal error. The front brain
owns the final chat reply; the UI no longer adds a duplicate failure message.
Stream deltas and orchestrator results carry their originating session id,
so a late result is not attributed to the front brain's most recent session.

`WebAppBrain` uses `ProjectSpec.web_stack`: `react_vite` (default for new
browser apps) or `static` (plain HTML/CSS/JS when explicitly selected).
React projects have src/main.tsx, src/App.tsx, src/styles.css and index.html.
The server owns package.json, tsconfig.json and vite.config.ts, with pinned
React 19, TypeScript, Vite and lucide-react dependencies. npm installation
disables lifecycle scripts; TypeScript and Vite run as explicit argv, without
a shell. The preview serves the built dist directory, including on UI rerun.

Install with `pip install -e '.[web]'` then
`python -m playwright install chromium`. Node >=20.19 and npm are required
for React builds. CI installs Chromium and its OS dependencies explicitly.

The architect and worker share the acceptance protocol in
`bigbrain/brains/web_acceptance.py`. New `tests/acceptance.json` files are
validated and saved in this canonical form before `workspace.file_written`:

```json
{
  "schema_version": 2,
  "cases": [{
    "name": "Open the application",
    "steps": [{"op": "click", "selector": "#complete"}, {"op": "reload"}],
    "assertions": [{"op": "checked", "selector": "#done", "value": true}]
  }]
}
```

`cases` and `assertions` must be non-empty arrays; `steps` is optional.
Operations are strictly validated data: click/fill/check/uncheck/select/press,
reload, viewport, visible/text/count/checked/value, storage_equals, no_overflow.
Arbitrary code and URLs are not accepted. Each case runs in a fresh ephemeral
profile. Old v1/descriptive formats remain readable, but browser verification
is inconclusive until executable v2 scenarios exist; prose is never a test pass.

The mandatory browser gate opens the production preview, verifies main
visibility, executes cases and captures JS/console errors, missing assets and
screenshots. External requests and service workers are blocked. Execution
is in a child process group with a 60s bound; Stop kills the driver and browser.
Missing Chromium produces an inconclusive verdict, never a pass.

At most two code repairs are allowed across build/browser errors. Existing
source files may be replaced; tests/toolchain/dependencies cannot be edited
by the repair response. Every attempt has immutable Evidence, source snapshots,
logs and up to three PNG screenshots. Attempts hash-link to the approved
DesignSpec and to previous attempts. The UI exposes results and screenshots
under Evidence. This verifies declared scenarios, not arbitrary completeness
or visual quality. The broader real-project campaign remains separate.

A worker returning `success=false` must retain that status in the bus result
envelope. The orchestrator then emits `task.failed` with the actual cause and
`runnable=false`. A failed run cannot inherit the launch metadata of the
previously selected project. The front brain reports the failure without an
LLM summary, and the docked card displays the cause even when collapsed.

Successful assembly emits `task.complete` with `project_path`, `entry_point`,
`deliverable_type`, `runnable` and the real `preview_url`. The docked React
card keeps its iframe and Open/Run controls visible. Regression coverage:
`tests/test_web_delivery.py` exercises the real bus and preview HTTP server;
`tests/test_web_browser.py` exercises Chromium, persistence, repair and Stop;
`tests/test_web_react.py` builds and type-checks real TSX, checks persistence in
Chromium and reruns production preview. `RunTimelineCard.test.tsx` checks the
collapsed render.
