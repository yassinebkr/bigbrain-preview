"""Research worker: bounded actions and actual page evidence over the bus."""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx

from .base import BaseBrain
from ..bus.message import BusMessage, MessageType, Priority
from ..research import DiscoveryPolicy, Limits, ModelPolicy, PageReader, ResearchRuntime
from ..research_assessment import ModelReviewer

logger = logging.getLogger(__name__)

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"


class BraveSearch:
    """Real Brave Search API client."""

    def __init__(self, api_key: str, max_results: int = 5):
        self.api_key = api_key
        self.max_results = max_results
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=15.0)
        return self._client

    async def search(self, query: str, count: int = None) -> List[Dict[str, Any]]:
        """Execute a single Brave search query.

        Returns list of {title, url, snippet, domain, age}.
        """
        count = count or self.max_results
        client = await self._get_client()

        try:
            resp = await client.get(
                BRAVE_SEARCH_URL,
                params={"q": query, "count": count},
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": self.api_key,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning("Brave search failed for '%s': %s", query, e)
            raise

        results = []
        for item in data.get("web", {}).get("results", [])[:count]:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("description", ""),
                "domain": urlparse(item.get("url", "")).netloc,
                "age": item.get("age", ""),
            })
        return results

    async def parallel_search(self, queries: List[str],
                               count_per_query: int = 5) -> Dict[str, List[Dict]]:
        """Execute multiple searches in parallel (LLMCompiler-style).

        Returns {query: [results]} mapping.
        """
        tasks = [self.search(q, count_per_query) for q in queries]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        out: Dict[str, List[Dict]] = {}
        for query, result in zip(queries, raw_results):
            if isinstance(result, Exception):
                logger.warning("Search '%s' failed: %s", query, result)
                out[query] = []
            else:
                out[query] = result
        return out

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()


class UnavailableSearch:
    """Honest no-op when no real search provider is configured."""

    async def search(self, query: str, count: int = 5) -> List[Dict[str, Any]]:
        return []

    async def parallel_search(self, queries: List[str],
                               count_per_query: int = 5) -> Dict[str, List[Dict]]:
        return {query: [] for query in queries}

    async def close(self):
        pass


class ResearcherBrain(BaseBrain):
    """Collect evidence using replaceable policies and runtime-owned observations."""

    def __init__(self, name: str, bus, workspace: str = "default",
                 llm_provider=None, search_provider=None,
                 brave_api_key: str = None,
                 max_searches: int = 5, max_results_per_search: int = 5,
                 page_reader=None, research_policy=None, research_reviewer=None):
        super().__init__(name, bus, workspace)
        self.llm_provider = llm_provider
        self.max_searches = max_searches
        self.max_results_per_search = max_results_per_search
        self.page_reader = page_reader or PageReader()
        self.research_policy = research_policy
        self.research_reviewer = research_reviewer

        # Never expose synthetic sources as evidence in a live run.
        if search_provider:
            self.search = search_provider
        elif brave_api_key:
            self.search = BraveSearch(brave_api_key, max_results_per_search)
        else:
            self.search = UnavailableSearch()
            logger.warning("No Brave API key — web research is unavailable")

    async def handle_task(self, message: BusMessage) -> Dict[str, Any]:
        """Handle research tasks using ReWOO pattern.

        Supported task types:
        - research: Full end-to-end research (plan → search → triangulate → summarize)
        - search_only: Just web search, return raw results
        """
        payload = message.payload
        task_type = payload.get("type", "research")
        # Explicit specialist input carries the resolved objective. Legacy
        # envelopes may still contain the raw conversational turn in user_request.
        query = (payload.get("query")
                 or payload.get("user_request")
                 or str(payload))

        if task_type == "search_only":
            return await self._search_only(query)
        else:
            return await self._full_research(query, payload)

    async def _full_research(self, query: str, payload: Dict) -> Dict[str, Any]:
        """Collect observations, then assess claims using inspected evidence."""
        start = time.monotonic()
        if isinstance(self.search, UnavailableSearch):
            state = await ResearchRuntime(self.search, self.page_reader, DiscoveryPolicy(), self.send_progress).run(
                query, unavailable_reason="No real search provider is configured; no sources were used.")
            return {"success": True, "research_unavailable": True, "research_status": "unavailable",
                    "query": query, "sources": [],
                    "summary": "Web research unavailable: no real search provider is configured; no sources were used.",
                    "top_sources": [], "unique_sources": 0, "unique_domains": 0,
                    "queries_used": [], "claims_verified": False, "evidence": state.model_dump(mode="json")}
        policy = self.research_policy or (ModelPolicy(self.llm_provider) if self.llm_provider else DiscoveryPolicy())
        runtime = ResearchRuntime(self.search, self.page_reader, policy, self.send_progress,
                                  cancelled=lambda: self._cancelled,
                                  limits=Limits(searches=max(1, min(self.max_searches, 5))),
                                  reviewer=self.research_reviewer or (ModelReviewer(self.llm_provider) if self.llm_provider else None))
        state = await runtime.run(query)
        sources = [s.model_dump(mode="json") for s in state.sources]
        read = [s for s in sources if s["status"] == "read"]
        lines = [state.reason or "Research incomplete."]
        for claim in state.claims:
            refs = ", ".join(link.passage_id for link in claim.evidence)
            lines.append(f"[{claim.status}] {claim.text} [{refs}] — {claim.basis}")
            lines.extend(f"Limit: {item}" for item in claim.limitations)
        lines.extend(f"Read: {s['url']}" for s in read)
        return {"success": state.status == "completed", "research_status": state.status,
                "query": query, "sources": sources,
                "error": state.reason if state.status == "partial" else None,
                "summary": "\n".join(lines), "claims_verified": False,
                "unique_sources": len(sources), "unique_domains": len({urlparse(s['url']).netloc for s in sources}),
                "top_sources": sources, "pages_read": len(read),
                "queries_used": [o.action.query for o in state.observations if o.action.tool == "search"],
                "evidence": state.model_dump(mode="json"),
                "execution_time": round(time.monotonic()-start, 2)}

    async def _search_only(self, query: str) -> Dict[str, Any]:
        """Just search, return raw results."""
        if isinstance(self.search, UnavailableSearch):
            return {"success": False, "research_unavailable": True, "query": query,
                    "results": [], "result_count": 0, "error": "No search provider configured"}
        try:
            results = await self.search.search(query, self.max_results_per_search)
        except Exception as exc:
            return {"success": False, "query": query, "results": [], "result_count": 0,
                    "error": str(exc)[:300], "pages_read": 0, "claims_verified": False}
        return {
            "success": True,
            "results": results,
            "query": query,
            "result_count": len(results),
            "pages_read": 0,
            "claims_verified": False,
        }

    # ── Bus message handling ─────────────────────────────────────────

    async def handle_message(self, message: BusMessage) -> None:
        """Handle non-task messages."""
        if (str(message.type) == "query"
                and message.payload.get("type") == "capabilities"):
            await self.send_result({
                "brain_type": "researcher",
                "search_provider": type(self.search).__name__,
                "has_llm": self.llm_provider is not None,
                "max_searches": self.max_searches,
                "max_results_per_search": self.max_results_per_search,
                "features": [
                    "brave_web_search",
                    "parallel_search",
                    "typed_actions",
                    "page_evidence",
                    "bounded_research",
                ],
            }, message.id)
        else:
            await super().handle_message(message)

    def get_status(self) -> Dict[str, Any]:
        base = super().get_status()
        return {
            **base,
            "brain_type": "researcher",
            "search_provider": type(self.search).__name__,
            "has_llm": self.llm_provider is not None,
        }

    async def stop(self) -> None:
        """Cleanup search client."""
        await self.search.close()
        await super().stop()
