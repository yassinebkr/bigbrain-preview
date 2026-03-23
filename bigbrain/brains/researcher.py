"""Researcher Brain — Web search + LLM analysis via ReWOO pattern.

All communication goes through the message bus:
- Search results → bus progress events
- LLM requests → bus task messages (or shared provider)
- Final results → bus result messages

Architecture: ReWOO + Source Triangulation
- Planner generates search queries from user request
- Parallel search execution (asyncio.gather)
- Source triangulation: cross-reference results, score confidence
- LLM summarization of findings
"""

import asyncio
import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx

from .base import BaseBrain
from ..bus.message import BusMessage, MessageType, Priority

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
            return []

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


class MockSearch:
    """Fallback when no Brave API key is available."""

    async def search(self, query: str, count: int = 5) -> List[Dict[str, Any]]:
        await asyncio.sleep(0.05)
        return [{
            "title": f"Mock result for: {query}",
            "url": f"https://example.com/{query.replace(' ', '-')[:30]}",
            "snippet": f"This is a mock search result for '{query}'. "
                       "Configure BRAVE_API_KEY for real web search.",
            "domain": "example.com",
            "age": "",
        }]

    async def parallel_search(self, queries: List[str],
                               count_per_query: int = 5) -> Dict[str, List[Dict]]:
        tasks = [self.search(q, count_per_query) for q in queries]
        raw = await asyncio.gather(*tasks)
        return dict(zip(queries, raw))

    async def close(self):
        pass


class ResearcherBrain(BaseBrain):
    """Researcher brain — web search + LLM analysis via message bus.

    ReWOO pattern:
    1. Plan: LLM generates search queries from user request
    2. Search: parallel Brave API calls (LLMCompiler-style speedup)
    3. Triangulate: cross-reference sources, score confidence
    4. Summarize: LLM synthesizes findings into coherent answer

    All LLM calls use the shared llm_provider (same OAuth as other brains).
    All progress/results go through the message bus.
    """

    def __init__(self, name: str, bus, workspace: str = "default",
                 llm_provider=None, search_provider=None,
                 brave_api_key: str = None,
                 max_searches: int = 5, max_results_per_search: int = 5):
        super().__init__(name, bus, workspace)
        self.llm_provider = llm_provider
        self.max_searches = max_searches
        self.max_results_per_search = max_results_per_search

        # Search provider: real Brave or mock fallback
        if search_provider:
            self.search = search_provider
        elif brave_api_key:
            self.search = BraveSearch(brave_api_key, max_results_per_search)
        else:
            self.search = MockSearch()
            logger.info("No Brave API key — using mock search")

    async def handle_task(self, message: BusMessage) -> Dict[str, Any]:
        """Handle research tasks using ReWOO pattern.

        Supported task types:
        - research: Full end-to-end research (plan → search → triangulate → summarize)
        - search_only: Just web search, return raw results
        """
        payload = message.payload
        task_type = payload.get("type", "research")
        query = (payload.get("user_request")
                 or payload.get("query")
                 or str(payload))

        if task_type == "search_only":
            return await self._search_only(query)
        else:
            return await self._full_research(query, payload)

    # ── Step 1: Plan search queries ──────────────────────────────────

    async def _plan_queries(self, user_request: str) -> List[str]:
        """Use LLM to generate targeted search queries from user request."""
        await self.send_progress({
            "stage": "planning",
            "request": user_request[:80],
        })

        if not self.llm_provider:
            # No LLM — extract keywords manually
            return self._fallback_queries(user_request)

        prompt = f"""Generate 3-5 specific web search queries to research this topic:

"{user_request}"

Rules:
- Each query should target a different angle (facts, data, expert opinions, recent news, technical details)
- Queries should be concise and search-engine optimized
- Output ONLY the queries, one per line, no numbering or bullets
- No explanations"""

        try:
            raw = await self.llm_provider.complete(prompt, stream=False, max_tokens=200)
            queries = [q.strip() for q in raw.strip().split("\n") if q.strip()]
            # Filter out empty or too-short queries
            queries = [q for q in queries if len(q) > 5][:self.max_searches]
            if queries:
                return queries
        except Exception as e:
            logger.warning("LLM query planning failed: %s", e)

        return self._fallback_queries(user_request)

    def _fallback_queries(self, user_request: str) -> List[str]:
        """Generate basic search queries without LLM."""
        base = user_request[:100]
        return [
            base,
            f"{base} latest research",
            f"{base} analysis data",
        ]

    # ── Step 2: Parallel search execution ────────────────────────────

    async def _execute_searches(self, queries: List[str]) -> Dict[str, List[Dict]]:
        """Run all searches in parallel via Brave API."""
        await self.send_progress({
            "stage": "searching",
            "query_count": len(queries),
            "queries": queries,
        })

        results = await self.search.parallel_search(queries, self.max_results_per_search)

        total_results = sum(len(r) for r in results.values())
        await self.send_progress({
            "stage": "search_complete",
            "total_results": total_results,
            "queries_with_results": sum(1 for r in results.values() if r),
        })

        return results

    # ── Step 3: Source triangulation ─────────────────────────────────

    def _triangulate(self, search_results: Dict[str, List[Dict]]) -> Dict[str, Any]:
        """Cross-reference sources and score confidence.

        Deterministic — no LLM needed.
        Checks: domain diversity, snippet overlap, source count.
        """
        all_results = []
        for query_results in search_results.values():
            all_results.extend(query_results)

        if not all_results:
            return {
                "confidence": 0.0,
                "unique_sources": 0,
                "domain_diversity": 0.0,
                "top_sources": [],
                "deduplicated": [],
            }

        # Deduplicate by URL
        seen_urls = set()
        deduped = []
        for r in all_results:
            url = r.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                deduped.append(r)

        # Domain diversity
        domains = set(r.get("domain", "") for r in deduped if r.get("domain"))
        domain_diversity = len(domains) / max(len(deduped), 1)

        # Snippet similarity — check for repeated key phrases across sources
        snippets = [r.get("snippet", "").lower() for r in deduped if r.get("snippet")]
        # Simple overlap: count how many snippet pairs share 3+ word sequences
        overlap_count = 0
        for i, s1 in enumerate(snippets):
            words1 = set(s1.split())
            for s2 in snippets[i + 1:]:
                words2 = set(s2.split())
                shared = words1 & words2
                if len(shared) >= 5:
                    overlap_count += 1

        # Confidence: more sources + more diversity + more agreement = higher
        source_score = min(len(deduped) / 10, 1.0)  # caps at 10 sources
        agreement_score = min(overlap_count / max(len(snippets), 1), 1.0)
        confidence = (source_score * 0.4 + domain_diversity * 0.3 + agreement_score * 0.3)

        # Rank by appearance frequency across queries
        url_freq: Dict[str, int] = {}
        for query_results in search_results.values():
            for r in query_results:
                url = r.get("url", "")
                if url:
                    url_freq[url] = url_freq.get(url, 0) + 1

        top_sources = sorted(deduped, key=lambda r: url_freq.get(r.get("url", ""), 0), reverse=True)

        return {
            "confidence": round(confidence, 3),
            "unique_sources": len(deduped),
            "unique_domains": len(domains),
            "domain_diversity": round(domain_diversity, 3),
            "agreement_score": round(agreement_score, 3),
            "top_sources": top_sources[:10],
            "deduplicated": deduped,
        }

    # ── Step 4: LLM summarization ───────────────────────────────────

    async def _summarize(self, user_request: str,
                          triangulation: Dict[str, Any]) -> str:
        """Use LLM to synthesize research findings into a coherent answer."""
        await self.send_progress({
            "stage": "summarizing",
            "source_count": triangulation["unique_sources"],
            "confidence": triangulation["confidence"],
        })

        if not self.llm_provider:
            # No LLM — return structured data instead
            sources = triangulation.get("top_sources", [])
            lines = [f"Found {triangulation['unique_sources']} sources "
                     f"(confidence: {triangulation['confidence']:.0%}):\n"]
            for s in sources[:5]:
                lines.append(f"- {s.get('title', 'Untitled')}: {s.get('snippet', '')[:100]}")
            return "\n".join(lines)

        # Build source context for LLM
        sources = triangulation.get("top_sources", [])[:8]
        source_text = ""
        for i, s in enumerate(sources, 1):
            source_text += (
                f"\n[Source {i}] {s.get('title', 'Untitled')}\n"
                f"URL: {s.get('url', '')}\n"
                f"Snippet: {s.get('snippet', '')}\n"
            )

        confidence = triangulation["confidence"]
        prompt = f"""Analyze these web search results and provide a comprehensive answer.

User's question: {user_request}

Search results ({triangulation['unique_sources']} sources, {triangulation['unique_domains']} domains, confidence: {confidence:.0%}):
{source_text}

Instructions:
- Synthesize the information into a clear, well-structured answer
- Cite sources by number [1], [2], etc. when making claims
- Note where sources agree or disagree
- If confidence is low (<50%), explicitly state what's uncertain
- Highlight the most important findings first
- Keep under 300 words — dense and useful"""

        try:
            summary = await self.llm_provider.complete(prompt, stream=False, max_tokens=600)
            return summary.strip()
        except Exception as e:
            logger.warning("LLM summarization failed: %s", e)
            # Fallback to raw sources
            lines = [f"Research found {len(sources)} sources (LLM summary unavailable):"]
            for s in sources[:5]:
                lines.append(f"- [{s.get('domain', '')}] {s.get('title', '')}: {s.get('snippet', '')[:120]}")
            return "\n".join(lines)

    # ── Full research workflow ───────────────────────────────────────

    async def _full_research(self, query: str, payload: Dict) -> Dict[str, Any]:
        """Complete ReWOO research pipeline: plan → search → triangulate → summarize."""
        start = time.time()

        # Step 1: Plan queries
        queries = await self._plan_queries(query)

        # Step 2: Parallel search
        search_results = await self._execute_searches(queries)

        # Step 3: Triangulate sources
        triangulation = self._triangulate(search_results)

        await self.send_progress({
            "stage": "triangulated",
            "confidence": triangulation["confidence"],
            "unique_sources": triangulation["unique_sources"],
        })

        # Step 4: Summarize with LLM
        summary = await self._summarize(query, triangulation)

        elapsed = time.time() - start

        return {
            "success": True,
            "summary": summary,
            "confidence": triangulation["confidence"],
            "unique_sources": triangulation["unique_sources"],
            "unique_domains": triangulation["unique_domains"],
            "domain_diversity": triangulation["domain_diversity"],
            "queries_used": queries,
            "top_sources": [
                {"title": s["title"], "url": s["url"], "domain": s["domain"]}
                for s in triangulation["top_sources"][:5]
            ],
            "execution_time": round(elapsed, 2),
        }

    async def _search_only(self, query: str) -> Dict[str, Any]:
        """Just search, return raw results."""
        results = await self.search.search(query, self.max_results_per_search)
        return {
            "success": True,
            "results": results,
            "query": query,
            "result_count": len(results),
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
                    "source_triangulation",
                    "llm_summarization",
                    "rewoo_pattern",
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
