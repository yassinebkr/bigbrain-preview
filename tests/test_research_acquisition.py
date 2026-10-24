"""Acquisition behavior on frozen sources and real Chromium with offline routes."""
import asyncio
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import AsyncMock

import httpx
import pytest

from bigbrain.research import Action, DiscoveryPolicy, Limits, PageReader, ResearchRuntime
from bigbrain.research_acquisition import PublicFetcher, ReadFailure, repository
from bigbrain.research_extraction import extract_html, window


def network(monkeypatch, respond):
    """Supply synthetic HTTP responses through the production pinned transport."""
    async def resolve(host, port, **kwargs):
        values = ["127.0.0.1"] if host == "private.test" else ["93.184.216.34"]
        if host == "mixed.test":
            values.append("127.0.0.1")
        return [(2, 1, 6, "", (ip, port)) for ip in values]
    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolve)
    calls = []
    async def transport(request):
        calls.append(request)
        assert request.url.host == "93.184.216.34"
        assert "authorization" not in request.headers
        assert "cookie" not in request.headers
        result = respond(request)
        return await result if asyncio.iscoroutine(result) else result
    cls = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: cls(transport=httpx.MockTransport(transport), **kwargs))
    return calls


def html_response(text, code=200, headers=None):
    return httpx.Response(code, headers={"content-type": "text/html", **(headers or {})}, content=text.encode())


@pytest.mark.asyncio
async def test_cache_windows_refresh_and_original_artifacts(monkeypatch):
    calls = network(monkeypatch, lambda request: html_response("<h1>Original v3 scope</h1><p>" + "intro "*3000 + "</p><p>Late signature and limits.</p>"))
    reader = PageReader()
    first = await reader.read("https://public.test/manual")
    focused = await reader.read("https://public.test/manual", focus="Late signature")
    assert "Late signature" in focused["text"]
    assert focused["acquisition"]["cache_hit"]
    assert len(calls) == 1
    assert first["sha256"] == focused["sha256"]
    raw = repository().get_artifact(first["sha256"])
    assert hashlib.sha256(raw).hexdigest() == first["sha256"]
    blocks = json.loads(repository().get_artifact(first["acquisition"]["blocks_artifact"]["sha256"]))
    assert any("Late signature" in b["text"] for b in blocks["original_blocks"])
    assert focused["blocks"][-1]["context"] == ["Original v3 scope"]
    await reader.read("https://public.test/manual", refresh=True)
    assert len(calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("code,status", [(401,"authentication_required"), (403,"blocked"), (429,"rate_limited"), (451,"blocked"), (503,"unavailable")])
async def test_access_failure_retains_response_but_creates_no_passage(monkeypatch, code, status):
    calls = network(monkeypatch, lambda request: html_response("<p>Access notice, not report evidence</p>", code))
    with pytest.raises(ReadFailure) as failed:
        await PageReader().read("https://public.test/report")
    assert failed.value.status == status
    ref = failed.value.record["raw_artifact"]
    assert b"Access notice" in repository().get_artifact(ref["sha256"])
    assert failed.value.record["record_artifact"]
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_all_dns_answers_and_redirects_are_checked(monkeypatch):
    calls = network(monkeypatch, lambda request: html_response("redirect",302,{"location":"https://private.test/internal"}))
    with pytest.raises(ReadFailure, match="Non-public"):
        await PageReader().read("https://mixed.test/")
    assert not calls
    with pytest.raises(ReadFailure) as failed:
        await PageReader().read("https://public.test/")
    assert failed.value.status == "unsafe_target"
    assert failed.value.record["requests"][0]["http_status"] == 302
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_redirect_cookie_is_not_sent_to_next_request(monkeypatch):
    def respond(request):
        if request.url.path == "/first":
            return html_response("",302,{"location":"/last","set-cookie":"private=secret; Path=/"})
        return html_response("<p>Final public document.</p>")
    calls = network(monkeypatch, respond)
    result = await PageReader().read("https://public.test/first")
    assert result["url"] == "https://public.test/last"
    assert len(result["acquisition"]["requests"]) == len(calls) == 2


@pytest.mark.asyncio
async def test_expired_and_evicted_cache_observations_are_refetched(monkeypatch):
    calls = network(monkeypatch, lambda request: html_response("<p>Original page.</p>"))
    reader = PageReader(cache_entries=1)
    await reader.read("https://public.test/a")
    await reader.read("https://public.test/b")
    await reader.read("https://public.test/a")
    assert len(reader.cache) == 1 and len(calls) == 3
    reader.cache_seconds = -1
    await reader.read("https://public.test/a")
    assert len(calls) == 4


def test_source_tables_code_and_heading_scope_survive_extraction():
    pytest.importorskip("trafilatura")
    html = '<h1>API v3 only</h1><table><tr><th>Metric</th><th>Value</th></tr><tr><td>Unknown</td><td></td></tr></table><pre>    if limit_ms &lt; 250:\n        emit("read_value")</pre>'
    result = extract_html(html, "https://public.test/ref")
    rows = [b["text"] for b in result["blocks"] if b["kind"] == "table_row"]
    assert "Unknown | " in rows
    code = next(b for b in result["blocks"] if b["kind"] == "code")
    assert code["text"] == '    if limit_ms < 250:\n        emit("read_value")'
    assert code["context"] == ["API v3 only"]


def test_literal_windows_report_clipped_original_blocks():
    selected, clipped = window([{"id":"b1", "text":"x"*13000, "kind":"code"}], limit=12000)
    assert clipped and selected[0]["clipped"]
    assert selected[0]["id"] == "b1" and selected[0]["block_end"] == 12000


class Policy:
    def __init__(self, *actions):
        self.actions = iter(actions)
    async def choose(self, state, remaining):
        return next(self.actions)


def act(tool, **kwargs):
    return Action(tool=tool, question_id="q1", rationale="Inspect missing directly relevant evidence", **kwargs)


@pytest.mark.asyncio
async def test_reopens_have_unique_passages_and_failed_focus_preserves_read(monkeypatch):
    network(monkeypatch, lambda request: html_response("<p>Observed signature with explicit limitations.</p>"))
    search = AsyncMock()
    search.search.return_value = [{"url":"https://public.test/"}]
    policy = Policy(act("search",query="API"), act("open",source_id="s1"),
                    act("open",source_id="s1",focus="signature"),
                    act("open",source_id="s1",focus="absent"), act("conclude"))
    state = await ResearchRuntime(search,PageReader(),policy,AsyncMock()).run("API")
    assert state.sources[0].status == "read"
    assert state.sources[0].acquisition["status"] == "focus_missing"
    assert len({p.id for p in state.passages}) == len(state.passages) == 2
    assert all(p.observation_sha256 for p in state.passages)


@pytest.mark.asyncio
@pytest.mark.parametrize("first", ["browser_first", "blocked", "budget"])
async def test_browser_requires_http_observation_and_its_own_budget(monkeypatch, first):
    network(monkeypatch, lambda request: html_response("<p>HTTP document</p>",403 if first=="blocked" else 200))
    search, browser = AsyncMock(), AsyncMock()
    search.search.return_value = [{"url":"https://public.test/"}]
    actions = [act("search",query="API")]
    if first != "browser_first":
        actions.append(act("open",source_id="s1"))
    actions.append(act("open",source_id="s1",mode="browser"))
    state = await ResearchRuntime(search,PageReader(browser=browser),Policy(*actions),AsyncMock(),
                                  limits=Limits(browsers=0 if first=="budget" else 2)).run("API")
    browser.render.assert_not_awaited()
    assert state.status == "partial"


@pytest.mark.asyncio
async def test_stop_interrupts_an_active_read_and_journals_terminal_state():
    started, closed = asyncio.Event(), asyncio.Event()
    cancelled = False
    class WaitingReader:
        async def read(self, url):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                closed.set()
    search, progress = AsyncMock(), AsyncMock()
    search.search.return_value = [{"url":"https://public.test/"}]
    runtime = ResearchRuntime(search,WaitingReader(),DiscoveryPolicy(),progress,cancelled=lambda:cancelled)
    task = asyncio.create_task(runtime.run("API"))
    await asyncio.wait_for(started.wait(),1)
    cancelled = True
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task,1)
    assert closed.is_set()
    assert runtime.state.status == "cancelled"
    assert progress.call_args.args[0]["stage"] == "research_finished"


@pytest.mark.asyncio
async def test_runtime_time_budget_limits_active_page_read():
    reader, search = AsyncMock(), AsyncMock()
    async def hang(url):
        await asyncio.Event().wait()
    reader.read.side_effect = hang
    search.search.return_value = [{"url":"https://public.test/"}]
    state = await ResearchRuntime(search,reader,DiscoveryPolicy(),AsyncMock(),limits=Limits(seconds=.05)).run("API")
    assert state.status == "partial" and "TimeoutError" in state.reason


@pytest.mark.asyncio
async def test_real_chromium_executes_script_and_data_through_public_transport(monkeypatch):
    api = pytest.importorskip("playwright.async_api")
    async with api.async_playwright() as pw:
        if not Path(pw.chromium.executable_path).is_file():
            pytest.skip("Playwright Chromium not installed")
    def respond(request):
        if request.url.path == "/":
            return html_response('<main id="app">Loading</main><script src="/app.js"></script>')
        if request.url.path == "/app.js":
            return httpx.Response(200,headers={"content-type":"application/javascript"},text='fetch("/data.json").then(r=>r.json()).then(v=>{document.querySelector("main").textContent=v.text}); fetch("https://private.test/internal").catch(()=>{}); fetch("/write",{method:"POST"}).catch(()=>{});')
        if request.url.path == "/data.json":
            return httpx.Response(200,headers={"content-type":"application/json"},json={"text":"Operating temperature: 5–35 °C, indoor use only."})
        raise AssertionError("Unexpected routed request: " + str(request.url))
    calls = network(monkeypatch,respond)
    reader = PageReader()
    static = await reader.read("https://public.test/")
    assert "Operating temperature" not in static["text"]
    rendered = await reader.read("https://public.test/",mode="browser")
    assert "5–35 °C" in rendered["text"]
    assert rendered["acquisition"]["mode"] == "browser"
    assert any("private.test" in r["url"] for r in rendered["acquisition"]["restrictions"])
    assert any("/write" in r["url"] for r in rendered["acquisition"]["restrictions"])
    assert [r.url.path for r in calls] == ["/","/app.js","/data.json"]
    assert repository().get_artifact(rendered["sha256"])


@pytest.mark.asyncio
async def test_real_chromium_cancellation_closes_inflight_resource(monkeypatch):
    pytest.importorskip("playwright.async_api")
    started, stopped = asyncio.Event(), asyncio.Event()
    phases = []
    async def respond(request):
        if request.url.path == "/":
            return html_response('<p>Loading report</p><script src="/pending.js"></script>')
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()
    network(monkeypatch,respond)
    reader = PageReader()
    await reader.read("https://public.test/")
    async def progress(info):
        phases.append(info["phase"])
    task = asyncio.create_task(reader.read("https://public.test/",mode="browser",progress=progress))
    await asyncio.wait_for(started.wait(),8)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task,5)
    assert stopped.is_set()
    assert "browser_closed" in phases


@pytest.mark.asyncio
async def test_production_reader_preserves_static_corpus_requirements(monkeypatch):
    pytest.importorskip("trafilatura")
    root = Path(__file__).parent / "fixtures" / "research_corpus"
    sys.path.insert(0,str(root))
    try:
        from evaluate import document_html, load, score
        corpus = load()
        content = {spec["url"]: document_html(spec) for spec in corpus["documents"].values()}
        def respond(request):
            original = "https://" + request.headers["host"] + request.url.path
            return html_response(content[original])
        network(monkeypatch,respond)
        reader = PageReader()
        for case in corpus["cases"]:
            if case["id"] in {"javascript","blocked"}:
                continue
            passages = {}
            for doc_id in case["documents"]:
                page = await reader.read(corpus["documents"][doc_id]["url"])
                passages[doc_id] = [block["text"] for block in page["blocks"]]
            result = score(case,corpus,{"passages":passages})
            assert result["passage_recall"] == 1,case["id"]
            assert not result["ungrounded_passage_documents"],case["id"]
    finally:
        sys.path.remove(str(root))


@pytest.mark.asyncio
async def test_real_chromium_request_budget_stops_resource_fanout(monkeypatch):
    pytest.importorskip("playwright.async_api")
    def respond(request):
        if request.url.path == "/":
            return html_response('<p>Loading report</p><script src="/app.js"></script>')
        if request.url.path == "/app.js":
            script = 'for(let i=0;i<30;i++) fetch("/data-"+i+".json").catch(()=>{});'
            return httpx.Response(200,headers={"content-type":"application/javascript"},text=script)
        return httpx.Response(200,headers={"content-type":"application/json"},json={"value":1})
    calls = network(monkeypatch,respond)
    reader = PageReader()
    await reader.read("https://public.test/")
    with pytest.raises(ReadFailure) as failed:
        await reader.read("https://public.test/",mode="browser")
    assert failed.value.status == "request_limit"
    assert len(calls) <= 20
    assert failed.value.record["requests"]
