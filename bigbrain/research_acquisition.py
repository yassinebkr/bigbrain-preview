"""HTTP acquisition, browser rendering and cached research observations.

PublicFetcher validates and pins network targets. BrowserReader renders pages
through that transport. PageReader stores source artifacts and selects a bounded
window of source-aligned blocks for the research runtime.
"""
from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import os
import socket
import time
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

import httpx

from .research_extraction import extract_html, window
from .research_context import select


class ReadFailure(ValueError):
    def __init__(self, status, message, *, record=None):
        super().__init__(message)
        self.status, self.record = status, dict(record or {})


@dataclass(frozen=True)
class Response:
    url: str
    status: int
    body: bytes
    headers: dict
    encoding: str
    artifact: dict
    chain: tuple

    def text(self):
        try:
            return self.body.decode(self.encoding, errors="replace")
        except LookupError:
            return self.body.decode("utf-8", errors="replace")


def repository():
    from .verification.evidence import default_repository
    return default_repository()


def artifact(body, *, name, media_type="application/json", metadata=None):
    return repository().put_artifact(body, name=name, media_type=media_type,
                                     metadata=metadata).model_dump(mode="json")


class PublicFetcher:
    """Fetch public GET responses and record each validated redirect hop."""
    max_bytes = 1_000_000

    async def fetch(self, url, *, redirects=True):
        chain = []
        async with httpx.AsyncClient(timeout=12, trust_env=False) as client:
            for _ in range(5):
                parsed = urlsplit(url)
                if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
                    raise ReadFailure("unsafe_target", "Only public HTTP(S) pages without credentials are supported", record={"requests": chain})
                try:
                    port = parsed.port or (443 if parsed.scheme == "https" else 80)
                except ValueError as exc:
                    raise ReadFailure("unsafe_target", "Invalid public target port") from exc
                if port not in {80, 443}:
                    raise ReadFailure("unsafe_target", "Unsupported public page port")
                addresses = await asyncio.get_running_loop().getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
                ips = [ipaddress.ip_address(item[4][0]) for item in addresses]
                if not ips or any(not ip.is_global for ip in ips):
                    raise ReadFailure("unsafe_target", "Non-public page address blocked", record={"requests": chain})
                ip = str(ips[0])
                host = f"[{ip}]" if ips[0].version == 6 else ip
                pinned = urlunsplit((parsed.scheme, f"{host}:{port}", parsed.path or "/", parsed.query, ""))
                # Responses may set cookies; research does not carry them across requests.
                client.cookies.clear()
                async with client.stream("GET", pinned, headers={"Host": parsed.netloc, "Connection": "close"},
                                         extensions={"sni_hostname": parsed.hostname}) as response:
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk[:self.max_bytes + 1-len(body)])
                        if len(body) > self.max_bytes:
                            raise ReadFailure("size_limit", "Page exceeds read size budget")
                    kind = response.headers.get("content-type", "application/octet-stream")
                    raw = bytes(body)
                    ref = artifact(raw, name="research-http-body", media_type=kind,
                                   metadata={"url": url, "http_status": response.status_code})
                    chain.append({"url": url, "http_status": response.status_code, "artifact": ref})
                    if response.is_redirect and redirects:
                        location = response.headers.get("location")
                        if not location:
                            raise ReadFailure("unavailable", "Redirect has no location", record={"requests": chain})
                        url = urljoin(url, location)
                        continue
                    return Response(url, response.status_code, raw, dict(response.headers),
                                    response.encoding or "utf-8", ref, tuple(chain))
        raise ReadFailure("redirect_limit", "Redirect budget exhausted", record={"requests": chain})


def check_response(response):
    code = response.status
    if code in {401, 407}:
        status = "authentication_required"
    elif code == 429:
        status = "rate_limited"
    elif code in {403, 451}:
        status = "blocked"
    elif code >= 400:
        status = "unavailable"
    else:
        return
    raise ReadFailure(status, f"HTTP {code}; content not accepted as page evidence",
                      record={"requests": list(response.chain), "raw_artifact": response.artifact})


class BrowserReader:
    """Render an observed HTML page in a fresh Chromium context.

    Request routing delegates allowed resources to PublicFetcher. The proxy and
    worker settings keep browser networking within the routed acquisition path.
    """
    async def render(self, initial, fetcher, *, progress):
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise ReadFailure("browser_unavailable", "Install .[web] and Playwright Chromium for rendered reads") from exc
        requests, restrictions, network_errors = [], [], []
        active_routes = set()
        spent, attempted, used_seed = 0, 0, False
        last_main = initial
        route_failure = None
        async with async_playwright() as playwright:
            try:
                browser = await playwright.chromium.launch(headless=True, proxy={"server": "http://127.0.0.1:9"},
                    args=["--disable-background-networking", "--disable-quic", "--proxy-bypass-list=<-loopback>",
                          "--force-webrtc-ip-handling-policy=disable_non_proxied_udp"])
            except Exception as exc:
                raise ReadFailure("browser_unavailable", "Chromium could not start; install Playwright Chromium") from exc
            context = None
            try:
                context = await browser.new_context(service_workers="block", accept_downloads=False, permissions=[])
                async def close_socket(ws):
                    await ws.close()
                await context.route_web_socket("**/*", close_socket)

                async def handle(route):
                    nonlocal spent, attempted, used_seed, last_main, route_failure
                    request = route.request
                    if request.method != "GET" or request.resource_type in {"image", "font", "media"}:
                        restrictions.append({"url": request.url[:500], "reason": "Resource type or write method excluded"})
                        await route.abort()
                        return
                    attempted += 1
                    await progress({"phase": "browser_request", "request_index": attempted,
                                    "resource_type": request.resource_type, "url": request.url[:500]})
                    if attempted > 20 or spent >= 4_000_000:
                        route_failure = ReadFailure("request_limit", "Browser request/byte budget exhausted")
                        await route.abort()
                        return
                    try:
                        if request.url == initial.url and not used_seed:
                            response, used_seed = initial, True
                        else:
                            response = await fetcher.fetch(request.url, redirects=False)
                        spent += len(response.body)
                        requests.extend(response.chain)
                        if spent > 4_000_000:
                            raise ReadFailure("size_limit", "Browser total byte budget exhausted")
                        if request.is_navigation_request() and request.frame.parent_frame is None:
                            last_main = response
                            check_response(response)
                        elif response.status >= 400:
                            network_errors.append(f"Resource HTTP {response.status}: {request.url[:300]}")
                        headers = {k: v for k, v in response.headers.items() if k.lower() in
                                   {"content-type", "content-security-policy", "location", "access-control-allow-origin"}}
                        await route.fulfill(status=response.status, headers=headers, body=response.body)
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        error = exc if isinstance(exc, ReadFailure) else ReadFailure("unavailable", str(exc)[:300])
                        restrictions.append({"url": request.url[:500], "reason": str(error)[:300]})
                        # A failed subresource is observable and may make a rendered
                        # page incomplete; it never becomes successful evidence.
                        if request.is_navigation_request() and request.frame.parent_frame is None:
                            route_failure = error
                        else:
                            network_errors.append(str(error)[:300])
                        await route.abort()

                async def tracked_route(route):
                    task = asyncio.current_task()
                    active_routes.add(task)
                    try:
                        await handle(route)
                    finally:
                        active_routes.discard(task)
                await context.route("**/*", tracked_route)
                await context.add_init_script("window.RTCPeerConnection = undefined; window.EventSource = undefined;")
                page = await context.new_page()
                page.on("dialog", lambda dialog: dialog.dismiss())
                page.set_default_timeout(5000)
                await progress({"phase": "browser_loading"})
                try:
                    await page.goto(initial.url, wait_until="domcontentloaded", timeout=12000)
                    try:
                        await page.wait_for_load_state("networkidle", timeout=2500)
                    except Exception:
                        network_errors.append("Network did not become idle within the render allowance")
                except Exception as exc:
                    if route_failure:
                        raise route_failure
                    raise ReadFailure("render_failed", "Browser navigation did not complete") from exc
                if route_failure:
                    raise route_failure
                # Redirect/JS navigation may change the document while reading.
                if urlsplit(page.url).scheme not in {"http", "https"}:
                    raise ReadFailure("unsafe_target", "Rendered document left HTTP(S)")
                dom = (await page.content()).encode("utf-8")
                if len(dom) > 1_000_000:
                    raise ReadFailure("size_limit", "Rendered DOM exceeds read size budget")
                ref = artifact(dom, name="research-rendered-dom.html", media_type="text/html",
                               metadata={"url": page.url, "browser_version": browser.version})
                return {"url": page.url, "body": dom, "artifact": ref, "requests": requests,
                        "restrictions": restrictions[:40], "limitations": network_errors[:20],
                        "browser_version": browser.version, "http_status": last_main.status}
            except ReadFailure as exc:
                # Failed rendering keeps the observed HTTP bodies and blocked
                # requests in the audit trail, alongside its explicit failure.
                exc.record.update(raw_artifact=initial.artifact, requests=requests,
                                  restrictions=restrictions[:40], limitations=network_errors[:20])
                raise
            finally:
                async def close():
                    try:
                        # Route callbacks can still await an HTTP resource when
                        # navigation is cancelled. Stop them before closing pages.
                        for task in list(active_routes):
                            task.cancel()
                        await asyncio.gather(*list(active_routes), return_exceptions=True)
                        if context:
                            await context.close()
                    finally:
                        await browser.close()
                        await progress({"phase": "browser_closed"})
                # Cleanup is bounded even when Stop cancelled navigation.
                await asyncio.wait_for(asyncio.shield(close()), timeout=3)


class PageReader:
    """Acquire, extract and cache immutable page observations for five minutes."""
    def __init__(self, *, fetcher=None, browser=None, cache_seconds=300, cache_entries=16):
        self.fetcher = fetcher or PublicFetcher()
        self.browser = browser or BrowserReader()
        self.cache_seconds, self.cache_entries = cache_seconds, cache_entries
        self.cache = OrderedDict()

    def cached_snapshot(self, url, mode='http'):
        """Return a fresh observation identity eligible for local consultation."""
        entry = self.cache.get((url, mode))
        if not entry or time.monotonic()-entry[0] >= self.cache_seconds:
            return None
        observed = entry[1]
        return (observed.get('rendered_artifact') or observed['raw_artifact'])['sha256']

    async def read(self, url, focus=None, *, mode="http", refresh=False, progress=None,
                   question=None, group_ids=(), observation_sha256=None, cached_snapshot=None, fragment=None,
                   coverage=False):
        if mode not in {"http", "browser"}:
            raise ReadFailure("invalid_mode", "Unknown acquisition mode")
        async def emit(data):
            if progress:
                await progress(data)
        try:
            async with asyncio.timeout(25 if mode == "browser" else 18):
                # A local consultation cannot silently become a network request
                # when its capture expires or is evicted before execution.
                if cached_snapshot and (refresh or self.cached_snapshot(url, mode) != cached_snapshot):
                    raise ReadFailure('cache_expired', 'Retained observation expired; a new acquisition requires budget')
                return await self._read(url, focus, mode, refresh, emit, question, group_ids, observation_sha256, fragment, coverage)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            failure = exc if isinstance(exc, ReadFailure) else ReadFailure(
                "timeout" if isinstance(exc, (TimeoutError, httpx.TimeoutException)) else "unavailable",
                "Page acquisition time budget exhausted" if isinstance(exc, (TimeoutError, httpx.TimeoutException)) else str(exc)[:300])
            failure.record.update(schema_version="1.0", status=failure.status, mode=mode)
            ref = artifact(json.dumps(failure.record, ensure_ascii=False).encode(), name="research-acquisition-failure.json")
            failure.record["record_artifact"] = ref
            raise failure from (exc if failure is not exc else None)

    async def _read(self, url, focus, mode, refresh, progress, question, group_ids, observation_sha256, fragment=None, coverage=False):
        key, now = (url, mode), time.monotonic()
        entry = self.cache.get(key)
        hit = bool(entry and not refresh and now-entry[0] < self.cache_seconds)
        # Cache entries retain their capture time and artifact identities. A hit
        # is a new consultation of that snapshot, rather than a fresh page fetch.
        if hit:
            self.cache.move_to_end(key)
            observed, prepared = entry[1:3]
            await progress({"phase": "cache_hit", "mode": mode})
        else:
            await progress({"phase": "http_loading", "mode": mode})
            http_entry = self.cache.get((url, "http")) if mode == "browser" and not refresh else None
            if http_entry and now-http_entry[0] < self.cache_seconds:
                response = http_entry[3]
                await progress({"phase": "http_cache_for_browser", "mode": mode})
            else:
                response = await self.fetcher.fetch(url)
            check_response(response)
            kind = response.headers.get("content-type", "").lower()
            if not any(t in kind for t in ("text/html", "text/plain", "application/xhtml+xml")):
                raise ReadFailure("unsupported", "Unsupported page content type; no text was read",
                                  record={"requests": list(response.chain), "raw_artifact": response.artifact})
            observed = {"schema_version": "1.0", "url": response.url, "mode": mode,
                        "captured_at": datetime.now(timezone.utc).isoformat(), "http_status": response.status,
                        "raw_artifact": response.artifact, "requests": list(response.chain), "limitations": []}
            text = response.text()
            if mode == "browser":
                if os.environ.get("BIGBRAIN_RESEARCH_BROWSER", "1") == "0":
                    raise ReadFailure("browser_unavailable", "Rendered reading disabled by configuration", record=observed)
                if "html" not in kind:
                    raise ReadFailure("unsupported", "Browser rendering requires an HTML observation", record=observed)
                rendered = await self.browser.render(response, self.fetcher, progress=progress)
                observed.update({"url": rendered["url"], "rendered_artifact": rendered["artifact"],
                                 "requests": rendered["requests"], "restrictions": rendered["restrictions"],
                                 "limitations": rendered["limitations"], "browser_version": rendered["browser_version"]})
                text = rendered["body"].decode("utf-8")
            await progress({"phase": "extracting", "mode": mode})
            prepared = await asyncio.to_thread(extract_html, text, observed["url"]) if "html" in kind else {
                "blocks": [{"id": "b1", "text": text, "kind": "plain_text", "locator": "body:text", "context": []}],
                "original_blocks": [], "title": "", "outline": [], "links": [], "engine": "plain-text", "limitations": [], "has_scripts": False}
            blocks_ref = artifact(json.dumps(prepared, ensure_ascii=False).encode(), name="research-source-blocks.json")
            observed.update(blocks_artifact=blocks_ref, engine=prepared["engine"], title=prepared["title"],
                            limitations=list(dict.fromkeys(observed["limitations"] + prepared["limitations"])))
            if mode == "browser":
                observed["limitations"] = [v for v in observed["limitations"] if not v.startswith("HTTP DOM alone")]
                observed["limitations"].append("Rendered DOM captured at a bounded instant; later changes are not observed")
            observed["record_artifact"] = artifact(json.dumps(observed, ensure_ascii=False).encode(), name="research-acquisition.json")
            self.cache[key] = (now, observed, prepared, response)
            self.cache.move_to_end(key)
            while len(self.cache) > self.cache_entries or sum(
                    item[1]["raw_artifact"]["size_bytes"] + item[1]["blocks_artifact"]["size_bytes"]
                    for item in self.cache.values()) > 8_000_000:
                self.cache.popitem(last=False)
        blocks = prepared["blocks"]
        # A literal focus may refer to a block omitted by main-text extraction.
        if focus:
            blocks = prepared["original_blocks"] or blocks
        if not any(b["text"].strip() for b in blocks):
            state = "requires_browser" if prepared["has_scripts"] and mode == "http" else "empty"
            raise ReadFailure(state, "No readable page text; rendered observation needed" if state == "requires_browser" else "No readable page text", record=observed)
        digest = (observed.get("rendered_artifact") or observed["raw_artifact"])["sha256"]
        # Keep a question-ranked route back into the immutable original page.
        # Source-order prefixes often contain the site's global navigation.
        from .research_context import groups, rank
        sections = groups(prepared["original_blocks"] or blocks, digest)
        ordered = rank(question or focus or "", sections)
        catalog = [{"id":sections[i]["id"], "context":[label[:160] for label in sections[i]["context"][-2:]],
                    "characters":sections[i]["characters"]} for i, _ in ordered[:96]]
        observed = {**observed, "navigation":{"observation_sha256":digest, "catalog":catalog,
                    "omitted_groups":max(0,len(sections)-len(catalog)), "order":"question-relevance"}}
        if group_ids and observation_sha256 != digest:
            raise ReadFailure("snapshot_changed", "Requested sections belong to another observation", record=observed)
        try:
            if fragment:
                # URL fragments select observed DOM entries within the same
                # captured page. They never create a synthetic evidence span.
                entry = [b for b in prepared['original_blocks'] if b.get('section_id') == unquote(fragment)]
                if not entry:
                    raise ValueError('Requested URL fragment was not observed in the page')
                selected, truncated = window(entry, focus)
                observed = {**observed, 'requested_fragment':fragment}
            elif (question or group_ids) and not focus:
                await progress({"phase":"selecting_context", "mode":mode})
                selected, selection = select(question or "",prepared["original_blocks"] or blocks,digest,
                                             requested=group_ids,preferred_ids={b["id"] for b in prepared["blocks"]},
                                             coverage=coverage)
                selection_ref = artifact(json.dumps(selection,ensure_ascii=False).encode(),name="research-context-selection.json")
                # Large indexes stay in the artifact; the decision context gets
                # bounded navigation metadata with an explicit omitted count.
                visible = {**selection,"catalog":selection["catalog"][:24],
                           "omitted_group_ids":selection["omitted_group_ids"][:24],
                           "omitted_group_count":len(selection["omitted_group_ids"]),
                           "catalog_truncated":len(selection["catalog"])>24}
                observed = {**observed,"selection":visible,"selection_artifact":selection_ref}
                truncated = selection["coverage"] != "complete"
                if selection["status"] == "needs_context":
                    raise ReadFailure("needs_context", "Section selection requires refinement; inspect the section catalog or use a literal focus",record=observed)
            else:
                selected, truncated = window(blocks, focus, document_title=prepared.get('title'))
        except ReadFailure:
            raise
        except ValueError as exc:
            raise ReadFailure("context_invalid" if group_ids else "focus_missing",str(exc),record=observed) from exc
        observed = {**observed, "cache_hit": hit, "status": "available", "truncated": truncated}
        return {"url": observed["url"], "text": "\n".join(b["text"] for b in selected), "sha256": digest,
                "blocks": selected, "links": list(dict.fromkeys(urljoin(observed["url"], l) for l in prepared["links"]))[:200],
                "truncated": truncated, "acquisition": observed}
