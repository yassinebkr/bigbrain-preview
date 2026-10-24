# Research acquisition — phase 3

Implemented on `feat/research-evidence`, 24 October 2026. This is phase 3 of the
acquisition/context sub-plan following the frozen corpus and extractor comparison.

## Components

- `research_acquisition.py`: public HTTP transport, browser rendering, immutable
  observations and a bounded per-reader cache.
- `research_extraction.py`: source-aligned Trafilatura XML, original table/code
  blocks, heading context and literal bounded windows.
- `research.py`: typed open actions, independent browser budget, acquisition
  progress, passage identities and cancellation of active work.

Install `.[research]` for Trafilatura 2.3.1 and BeautifulSoup. Rendered reads
additionally use the existing `.[web]` Playwright dependency and Chromium:
`python -m playwright install chromium`. `BIGBRAIN_RESEARCH_BROWSER=0` disables
rendered reads. An environment missing the research extra retains explicitly
labeled unfiltered extraction; missing Chromium reports `browser_unavailable`.

## Execution

An `open` starts with `mode=http`. A later `open` for the same source may specify
`mode=browser` with the policy's rationale when required content is missing.
The runtime requires an HTTP observation and a remaining browser allowance.
Blocked, authentication-required and rate-limited responses stop that access
path. A script-only empty HTTP document reports `requires_browser`.
The model chooses the next action from observed evidence gaps.

All allowed browser requests are fulfilled by the same DNS-pinned Python
transport, including scripts and GET data requests. Every DNS answer must be
public, redirects are checked at each hop, and the connection uses the validated
IP with the original Host/TLS SNI. The transport ignores environment proxies and
does not carry cookies or authentication headers between requests. Browser
contexts are ephemeral, with service workers, WebSockets, downloads and write
requests blocked. Images/fonts/media are excluded from this text-acquisition
path; their absence is recorded among rendering restrictions. A dead browser
proxy and WebRTC settings provide an additional boundary around routed traffic.

The source-aligned extractor retains original code indentation, table values and
empty cells. Extracted blocks map back to original DOM blocks; original table
rows are restored when the main-text extractor omits them. Original titles,
headings, links and all indexed blocks are retained in a separate artifact.
Each selected passage has its own observation hash, source locator, heading
context and clipping flag. Reopening a source creates new passage IDs. A failed
later read keeps the earlier successfully read passages available.

`focus` is a literal term chosen by the policy. It can reopen cached original
blocks omitted by main-text extraction using a bounded window. Phase 4 now adds
question-based section selection and observation-bound section refinement;
see [`RESEARCH_CONTEXT.md`](RESEARCH_CONTEXT.md). The 12,000-character window
remains the literal-focus/legacy path; question selection defaults to 6,000.

## Bounds and audit

Defaults: 90 seconds per research run, 6 page attempts, 2 browser attempts,
18 seconds per HTTP read, 25 seconds per rendered read, at most 5 HTTP hops,
1 MB per HTTP response/rendered DOM and 12,000 selected characters per page.
A browser render allows at most 20 routed GET requests and 4 MB of routed bodies,
including its seeded main document; the preceding HTTP redirect chain has its
own per-response/hop limits. Browser idle waiting is limited to 2.5 seconds.
The complete defaults and counts are recorded in the research state.

The cache expires after 300 seconds and holds at most 16 observations, with an
8 MB accounting limit for raw-body and block-artifact payload sizes. These are
payload bounds rather than a claim about total Python resident memory.
Cache hits preserve capture time, record identity and an explicit hit flag;
`refresh=true` asks for a new observation. Rendering reuses an available HTTP
snapshot instead of fetching that main document again.

HTTP bodies, rendered DOM, indexed blocks and request records use the existing
content-addressed EvidenceRepository under `BIGBRAIN_EVIDENCE_ROOT`. A cache
eviction does not delete retained evidence. Request failures preserve observed
bodies and restrictions in their diagnostic artifact. No new retention/deletion
policy is introduced in this phase.

Progress includes HTTP loading, cached reads, extraction, browser requests and
browser closure. The runtime's Stop watcher cancels an active read/provider wait.
Renderer cleanup cancels pending resource callbacks and closes its context and
browser, with a bounded cleanup allowance. Successful observations survive Stop.

## Validation and limits

Full regression: 1,445 passed, 8 skipped, 9 warnings in 175.87 seconds. The eight
skips are optional phase-2 benchmark cases requiring Markdownify in addition to
the runtime research dependencies; they previously passed in their isolated
benchmark environment. The final acquisition suite, including an additional
resource-ceiling/audit check, passed 21 tests after the full regression.
No UI source changed in this phase. Existing unrelated working-tree changes
and local memory files were preserved.

Production-reader tests cover the frozen static gold passages, original
code/units/empty cells and heading scope, cache/refresh/expiry, immutable bodies,
DNS mixing and redirects, excluded cookies, access-status diagnostics, browser
prerequisites/budgets, unique passages, missing focus, overall timeout and Stop.

Real Chromium tests use fully synthetic HTTP responses through the actual routed
transport. They execute an external script, fetch JSON, obtain rendered content,
block a private destination and a POST, interrupt an in-flight script and enforce
the resource request ceiling. They exercise Chromium, not a replayed rendered
fixture. Test artifacts are isolated by conftest.

A separate public connectivity check read Python's pathlib documentation with
literal focus `Path.unlink`: 4,526 selected characters across 74 blocks, followed
by a cache hit on the same snapshot. Its raw SHA-256 was
`48d51a2ae53b38654c0bb765518e39136d936a1244f3252dfb2ea7e4ef22ae59`.
Artifacts were written under a disposable `/tmp` evidence root. No model or Brave
API call, personal memory or user project was involved.

The tests establish acquisition behavior, not real-web research quality or
universal access through anti-bot controls. Delayed interactions, login/paywall
flows, PDFs, OCR and semantic research quality have separate requirements.
Phase-4 context-selection measurements are documented separately. Rendered DOM is a bounded-time observation rather than a screenshot
or guarantee that later page changes were observed. Browser and extraction
limitations remain available to the policy/reviewer and durable journal.
