"""DEPRECATED 2026-04-14 — see src/research_pipeline/DEPRECATED.md

Researcher agents. Dormant dependency of drift_monitor. Executes individual
research tasks via search APIs. No longer an active ingestion path.

Input: single ResearchTask
Output: ResearchResult (claim, elaboration, sources, confidence_score, domain)
Tools: Tavily search, Exa search, web fetch via httpx
Max 3 tool calls per researcher. Rate limiting: per-domain, max 10 req/min.
"""

import os
import time
import hashlib
from collections import defaultdict
from datetime import datetime
from threading import Lock
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()

from pydantic import BaseModel, Field

from langchain_anthropic import ChatAnthropic
from tavily import TavilyClient
from exa_py import Exa
import httpx

from src.research_pipeline.planner import ResearchTask


# ── Output models ──


class Source(BaseModel):
    """A single source backing a research finding."""

    url: str = ""
    title: str = ""
    snippet: str = ""
    source_type: str = Field(
        default="other",
        description="One of: academic, journalism, book, social_media, government, primary, other",
    )
    reliability_note: str = Field(
        default="",
        description="Brief assessment of source reliability",
    )


class ResearchResult(BaseModel):
    """Structured output from a single Researcher agent."""

    task_id: str = ""
    claim: str = Field(
        default="",
        description="The core finding as a precise claim (target 280 chars)",
    )
    elaboration: str = Field(
        default="",
        description="Full explanation of the finding with nuance",
    )
    sources: list[Source] = Field(
        default_factory=list,
        description="Sources that support this claim",
    )
    confidence_score: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="How confident are you in this claim? 0.0-1.0",
    )
    confidence_basis: str = Field(
        default="",
        description="Why this confidence score was assigned",
    )
    domain: str = Field(
        default="",
        description="The knowledge domain, e.g. 'political psychology'",
    )


# ── Rate limiter ──


class DomainRateLimiter:
    """Per-domain rate limiting: max 10 requests/minute per domain."""

    def __init__(self, max_per_minute: int = 10):
        self._max = max_per_minute
        self._timestamps: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def wait_if_needed(self, url: str) -> None:
        domain = urlparse(url).netloc if url.startswith("http") else url
        with self._lock:
            now = time.time()
            window_start = now - 60.0
            # Prune old timestamps
            self._timestamps[domain] = [
                t for t in self._timestamps[domain] if t > window_start
            ]
            if len(self._timestamps[domain]) >= self._max:
                sleep_time = self._timestamps[domain][0] - window_start
                if sleep_time > 0:
                    time.sleep(sleep_time)
            self._timestamps[domain].append(time.time())


_rate_limiter = DomainRateLimiter(max_per_minute=10)


# ── Search tools ──


def search_tavily(query: str, max_results: int = 5) -> list[dict]:
    """Search via Tavily API. Returns list of {url, title, content}."""
    _rate_limiter.wait_if_needed("api.tavily.com")
    client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    response = client.search(
        query=query,
        max_results=max_results,
        search_depth="advanced",
        include_raw_content=False,
    )
    return [
        {
            "url": r.get("url", ""),
            "title": r.get("title", ""),
            "content": r.get("content", "")[:2000],
        }
        for r in response.get("results", [])
    ]


def search_exa(query: str, max_results: int = 5) -> list[dict]:
    """Search via Exa semantic search API. Returns list of {url, title, content}."""
    _rate_limiter.wait_if_needed("api.exa.ai")
    client = Exa(api_key=os.environ["EXA_API_KEY"])
    response = client.search_and_contents(
        query=query,
        num_results=max_results,
        text={"max_characters": 2000},
        type="auto",
    )
    return [
        {
            "url": r.url,
            "title": r.title or "",
            "content": (r.text or "")[:2000],
        }
        for r in response.results
    ]


def search_semantic_scholar(query: str, max_results: int = 5) -> list[dict]:
    """Search via Semantic Scholar public API. No API key required.

    Rate limit: 100 requests/minute per their public API terms.
    Returns list of {url, title, content} matching the search tools format.
    """
    _rate_limiter.wait_if_needed("api.semanticscholar.org")
    last_error = None
    for attempt in range(3):
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(
                    "https://api.semanticscholar.org/graph/v1/paper/search",
                    params={
                        "query": query,
                        "limit": max_results,
                        "fields": "title,abstract,url,year,citationCount,authors",
                    },
                    headers={"User-Agent": "Explodable Research Agent/1.0"},
                )
                if resp.status_code == 429:
                    time.sleep(2 ** attempt)  # 1s, 2s, 4s backoff
                    last_error = RuntimeError(f"Semantic Scholar rate limited (attempt {attempt + 1})")
                    continue
                resp.raise_for_status()
                data = resp.json()
                break
        except httpx.HTTPError as e:
            last_error = RuntimeError(f"Semantic Scholar API error: {e}")
            break
    else:
        raise last_error or RuntimeError("Semantic Scholar API: max retries exceeded")

    results = []
    for paper in data.get("data", []):
        authors = ", ".join(a.get("name", "") for a in (paper.get("authors") or [])[:3])
        year = paper.get("year", "")
        citations = paper.get("citationCount", 0)
        abstract = paper.get("abstract") or ""

        content = abstract
        if authors or year:
            content = f"Authors: {authors} ({year}). Citations: {citations}.\n{abstract}"

        results.append({
            "url": paper.get("url") or f"https://www.semanticscholar.org/paper/{paper.get('paperId', '')}",
            "title": paper.get("title", ""),
            "content": content[:2000],
        })
    return results


def fetch_url(url: str) -> dict:
    """Fetch a URL and return its text content (truncated)."""
    _rate_limiter.wait_if_needed(url)
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            resp = client.get(url, headers={"User-Agent": "Explodable Research Agent/1.0"})
            resp.raise_for_status()
            return {
                "url": url,
                "title": "",
                "content": resp.text[:5000],
            }
    except httpx.HTTPError as e:
        return {"url": url, "title": "", "content": f"Fetch failed: {e}"}


# ── Researcher agent ──

RESEARCHER_SYSTEM_PROMPT = """You are a research agent for an intelligence engine. You receive a research task and search results, and must produce a single precise finding.

Your job:
1. Analyze the search results provided
2. Synthesize them into ONE clear, precise claim (max 280 characters)
3. Write a full elaboration explaining the finding with nuance
4. Assess your confidence based on source quality and agreement
5. Classify each source by type

Confidence scoring guide:
- 0.85-1.0: Multiple high-quality sources converge on the same conclusion
- 0.70-0.84: Good evidence from reliable sources with minor gaps
- 0.50-0.69: Moderate evidence, some disagreement or limited sources
- 0.30-0.49: Weak evidence, mostly speculative or single-source
- 0.0-0.29: Very weak, contradictory, or no real evidence found

Source types: academic, journalism, book, social_media, government, primary, other

Be honest about confidence. A low-confidence finding with clear basis is more valuable than an inflated score."""


class ResearchToolsExhaustedError(Exception):
    """Raised when all search tools fail for a research task."""
    pass


def _gather_search_results(task: ResearchTask) -> list[dict]:
    """Run up to 3 tool calls: Tavily + Exa + optional URL fetch.

    Max 3 tool calls per researcher per spec.
    Raises ResearchToolsExhaustedError if all search tools fail.
    """
    import structlog
    logger = structlog.get_logger()

    results = []
    tool_calls = 0
    tool_failures = 0

    # Tool call 1: Tavily search
    query = " ".join(task.search_keywords[:3])
    try:
        tavily_results = search_tavily(query, max_results=5)
        results.extend(tavily_results)
        tool_calls += 1
    except Exception as e:
        tool_failures += 1
        logger.error(
            "researcher.tool_failed",
            tool="tavily",
            task_id=task.task_id,
            query=query,
            error=str(e),
            error_type=type(e).__name__,
        )

    # Tool call 2: Exa semantic search (uses the full question for better semantic match)
    if tool_calls < 3:
        try:
            exa_results = search_exa(task.query, max_results=5)
            results.extend(exa_results)
            tool_calls += 1
        except Exception as e:
            tool_failures += 1
            logger.error(
                "researcher.tool_failed",
                tool="exa",
                task_id=task.task_id,
                query=task.query[:100],
                error=str(e),
                error_type=type(e).__name__,
            )

    # Tool call 3: Semantic Scholar (academic papers, no API key required)
    if tool_calls < 3:
        try:
            scholar_results = search_semantic_scholar(task.query, max_results=5)
            results.extend(scholar_results)
            tool_calls += 1
        except Exception as e:
            tool_failures += 1
            logger.error(
                "researcher.tool_failed",
                tool="semantic_scholar",
                task_id=task.task_id,
                query=task.query[:100],
                error=str(e),
                error_type=type(e).__name__,
            )

    # Tool call 4 (bonus): Fetch the most promising URL if we have capacity
    if tool_calls < 3 and results:
        # Pick the first result that looks like a substantive source
        for r in results:
            url = r.get("url", "")
            if url and len(r.get("content", "")) < 200:
                try:
                    fetched = fetch_url(url)
                    if "Fetch failed" not in fetched["content"]:
                        r["content"] = fetched["content"][:2000]
                    tool_calls += 1
                    break
                except Exception as e:
                    logger.error(
                        "researcher.tool_failed",
                        tool="fetch_url",
                        task_id=task.task_id,
                        url=url,
                        error=str(e),
                        error_type=type(e).__name__,
                    )

    # If all primary search tools failed, do not synthesize from nothing
    if not results and tool_failures >= 2:
        raise ResearchToolsExhaustedError(
            f"All search tools failed for task {task.task_id}: "
            f"{tool_failures} failures, 0 results. Cannot synthesize from nothing."
        )

    return results


def _deduplicate_results(results: list[dict]) -> list[dict]:
    """Remove duplicate URLs from search results."""
    seen_urls: set[str] = set()
    deduped = []
    for r in results:
        url = r.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            deduped.append(r)
        elif not url:
            deduped.append(r)
    return deduped


def research_task(task: ResearchTask) -> ResearchResult:
    """Execute a single research task: gather sources, synthesize into a finding.

    Args:
        task: A ResearchTask from the planner.

    Returns:
        ResearchResult with claim, elaboration, sources, confidence, domain.
    """
    # Gather search results (max 3 tool calls)
    raw_results = _gather_search_results(task)
    results = _deduplicate_results(raw_results)

    # Format results for the LLM
    context_parts = []
    for i, r in enumerate(results[:10], 1):
        context_parts.append(
            f"Source {i}:\n"
            f"  URL: {r['url']}\n"
            f"  Title: {r['title']}\n"
            f"  Content: {r['content'][:1500]}\n"
        )
    context = "\n".join(context_parts)

    # Synthesize via Claude
    from src.shared.constants import ANTHROPIC_MODEL
    llm = ChatAnthropic(
        model=ANTHROPIC_MODEL,
        temperature=0.2,
        max_tokens=2000,
        max_retries=5,
    ).with_structured_output(ResearchResult)

    result = llm.invoke(
        [
            {"role": "system", "content": RESEARCHER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Research task: {task.query}\n"
                    f"Expected domain: {task.expected_domain}\n"
                    f"Task ID: {task.task_id}\n\n"
                    f"Search results:\n{context}\n\n"
                    f"Synthesize these into a single finding with the structured format."
                ),
            },
        ]
    )

    return result
