"""Web search and URL extraction tools for the avatar agent.

Search uses the Tavily Search API (via langchain-tavily), with DuckDuckGo
fallback when no Tavily key is set. URL extraction uses Tavily Extract and
requires a Tavily API key (no DuckDuckGo equivalent).
"""

import logging
import re
from typing import Optional
from urllib.parse import urlparse

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# Stop at whitespace, angle brackets, or straight double-quote (common in HTML).
_URL_IN_TEXT = re.compile(r"https?://[^\s<>\"]+", re.IGNORECASE)

_TOOL_DESCRIPTION = """MANDATORY: Call this tool BEFORE writing any text in two cases:

CASE 1 — USER ASKS ABOUT DYNAMIC TOPICS (reactive):
- Sports results or standings (F1, football, tennis, basketball, any sport)
- Current news or recent events
- Current prices (dollar, crypto, stocks, commodities)
- Weather or forecasts
- Recent releases (movies, series, music, games)
- Any data that may have changed in the last few days

CASE 2 — PROACTIVE FACTUAL VERIFICATION (autonomous — no user prompt needed):
Before asserting any external verifiable fact — figures, dates, who won something, whether a
law is still in force, whether a product exists, whether something is "still" the case — call
this tool FIRST, even if the user did NOT ask you to search.
Do not wait to be told. If the fact might be outdated or wrong, verify it.

DO NOT announce that you will search. DO NOT say "give me a moment" or "I'll look it up".
Search silently: CALL THIS TOOL FIRST, then respond with the results.

Args:
    query: Specific search query. Include date references when relevant for fresher results.

Returns:
    Formatted search results with titles, snippets, and sources.
"""

_FETCH_URLS_DESCRIPTION = """Use when the user pastes one or more specific URLs (http/https) or asks you to read, summarize, or answer from particular links or articles.

Call this BEFORE writing an answer — do not say you will read the page; invoke the tool first.

This extracts text from those exact pages (not a general web search). For open-ended current events without specific links, use web_search instead.

Args:
    urls: List of full URLs (https://...). You may include strings that contain multiple URLs; they will be parsed.
    query: Optional focus question — helps prioritize relevant sections in long pages (e.g. user's question).

Returns:
    Extracted text per URL (titles, content snippets). May note failures per link.
"""


def normalize_http_urls(urls: list[str], max_urls: int) -> list[str]:
    """Collect unique http(s) URLs from free-form strings (and bare www. hosts).

    Args:
        urls: Raw strings from the model (may contain one URL or several per string).
        max_urls: Cap on how many URLs to return.

    Returns:
        Ordered unique URLs, at most ``max_urls``.
    """
    seen: set[str] = set()
    out: list[str] = []
    for item in urls:
        if not isinstance(item, str) or not item.strip():
            continue
        found_in_item = False
        for m in _URL_IN_TEXT.finditer(item):
            found_in_item = True
            u = m.group(0).rstrip(".,);]>\"" "'")
            if u not in seen:
                seen.add(u)
                out.append(u)
            if len(out) >= max_urls:
                return out
        if not found_in_item:
            s = item.strip()
            if s.lower().startswith("www."):
                first = s.split()[0].rstrip(".,);]>\"" "'")
                u = "https://" + first
                parsed = urlparse(u)
                if parsed.netloc and u not in seen:
                    seen.add(u)
                    out.append(u)
                if len(out) >= max_urls:
                    return out
    return out[:max_urls]


def _format_extract_results(payload: dict | list | str) -> str:
    """Format Tavily Extract API response for the LLM."""
    if isinstance(payload, str):
        return payload
    if not isinstance(payload, dict):
        return "No se pudo leer el contenido de los enlaces."

    lines: list[str] = []
    for fr in payload.get("failed_results") or []:
        if isinstance(fr, dict):
            url = fr.get("url", "?")
            err = fr.get("error", fr.get("reason", "error desconocido"))
            lines.append(f"- Fallo al leer {url}: {err}")

    max_chars_per_page = 12_000
    for item in payload.get("results") or []:
        if not isinstance(item, dict):
            continue
        url = item.get("url", "")
        title = item.get("title", "Sin título")
        raw = item.get("raw_content") or item.get("content") or ""
        lines.append(f"### {title}")
        lines.append(f"**URL:** {url}")
        if raw:
            text = str(raw).strip()
            if len(text) > max_chars_per_page:
                text = text[:max_chars_per_page] + "\n\n[... contenido truncado ...]"
            lines.append(text)
        lines.append("")

    if not lines:
        return "No se pudo extraer texto de ninguno de los enlaces."
    return "\n".join(lines).strip()


def build_fetch_urls_tool(
    tavily_api_key: Optional[str],
    max_urls: int = 5,
):
    """Build Tavily Extract-based tool, or return None without an API key."""
    if not tavily_api_key:
        return None

    from langchain_tavily import TavilyExtract

    extractor = TavilyExtract(
        tavily_api_key=tavily_api_key,
        extract_depth="advanced",
        include_images=False,
    )

    @tool(description=_FETCH_URLS_DESCRIPTION)
    async def fetch_urls(urls: list[str], query: Optional[str] = None) -> str:
        normalized = normalize_http_urls(urls, max_urls)
        if not normalized:
            return (
                "No recibí enlaces http(s) válidos. Pasá la URL completa "
                "(por ejemplo https://...)."
            )
        logger.info("Executing Tavily extract: urls=%s query=%r", normalized, query)
        try:
            payload = await extractor.ainvoke({"urls": normalized, "query": query})
            return _format_extract_results(payload)
        except Exception:
            logger.exception("Tavily extract failed: urls=%s", normalized)
            return "No pude leer esos enlaces en este momento."

    return fetch_urls


def build_web_search_tool(
    tavily_api_key: Optional[str] = None,
    max_results: int = 3,
):
    """Build and return the appropriate web search tool.

    Returns a Tavily-backed tool when a valid API key is provided,
    otherwise falls back to DuckDuckGo (no API key required).

    Args:
        tavily_api_key: Tavily Search API key. If empty or None, falls back
            to DuckDuckGo.
        max_results: Maximum number of search results to include in the
            response. Defaults to 3.

    Returns:
        A LangChain tool callable for web searching.
    """
    if tavily_api_key:
        return _build_tavily_tool(tavily_api_key=tavily_api_key, max_results=max_results)
    return _build_duckduckgo_tool(max_results=max_results)


def _build_tavily_tool(tavily_api_key: str, max_results: int):
    """Build a Tavily-backed web search tool.

    Args:
        tavily_api_key: Valid Tavily API key.
        max_results: Maximum number of results to return.

    Returns:
        A LangChain tool that searches via Tavily.
    """
    from langchain_tavily import TavilySearch

    tavily = TavilySearch(
        max_results=max_results,
        tavily_api_key=tavily_api_key,
        search_depth="advanced",
        include_answer=True,
        include_raw_content=False,
        include_images=False,
    )

    @tool(description=_TOOL_DESCRIPTION)
    async def web_search(query: str) -> str:
        logger.info("Executing Tavily web search: query=%r", query)
        try:
            results = await tavily.ainvoke(query)
            formatted = _format_results(results)
            # Phase 15: stash for the engagement classifier to read on the
            # next turn. No-ops when called outside a bound chat request.
            try:
                from app.services.search_engagement_service import (
                    stash_search_context_for_current_chat,
                )

                stash_search_context_for_current_chat(query, formatted[:1000])
            except Exception:
                logger.debug("Search-engagement stash failed", exc_info=True)
            return formatted
        except Exception:
            logger.exception("Tavily web search failed: query=%r", query)
            return "No pude obtener resultados de búsqueda en este momento."

    return web_search


def _build_duckduckgo_tool(max_results: int):
    """Build a DuckDuckGo-backed web search tool (no API key required).

    Args:
        max_results: Maximum number of results to return.

    Returns:
        A LangChain tool that searches via DuckDuckGo.
    """
    from langchain_community.tools import DuckDuckGoSearchResults
    from langchain_community.utilities import DuckDuckGoSearchAPIWrapper

    logger.warning(
        "No TAVILY_API_KEY configured — falling back to DuckDuckGo search. "
        "Results may be less accurate for real-time queries."
    )

    wrapper = DuckDuckGoSearchAPIWrapper(max_results=max_results)
    ddg = DuckDuckGoSearchResults(api_wrapper=wrapper, output_format="list")

    @tool(description=_TOOL_DESCRIPTION)
    async def web_search(query: str) -> str:
        logger.info("Executing DuckDuckGo web search: query=%r", query)
        try:
            results = await ddg.ainvoke(query)
            formatted = _format_results(results)
            try:
                from app.services.search_engagement_service import (
                    stash_search_context_for_current_chat,
                )

                stash_search_context_for_current_chat(query, formatted[:1000])
            except Exception:
                logger.debug("Search-engagement stash failed", exc_info=True)
            return formatted
        except Exception:
            logger.exception("DuckDuckGo web search failed: query=%r", query)
            return "No pude obtener resultados de búsqueda en este momento."

    return web_search


def _format_results(results: dict | list | str) -> str:
    """Format raw search results into a readable string.

    Handles three possible shapes:
    - str: pre-formatted string (pass through).
    - dict: Tavily response ``{"answer": str, "results": list[dict], ...}``.
    - list: DuckDuckGo response (list of dicts with title/content/url keys).

    Args:
        results: Raw results from Tavily or DuckDuckGo.

    Returns:
        A formatted string with numbered results, titles, snippets, and URLs.
    """
    if isinstance(results, str):
        return results

    # Tavily returns a dict with "answer" and "results" keys
    if isinstance(results, dict):
        items: list[dict] = results.get("results") or []
        answer: str = results.get("answer") or ""
        lines: list[str] = []
        if answer:
            lines.append(f"**Resumen:** {answer}\n")
        for i, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            title = item.get("title", "Sin título")
            content = item.get("content", item.get("snippet", ""))
            url = item.get("url", item.get("link", ""))
            lines.append(f"{i}. **{title}**")
            if content:
                snippet = content[:300].rstrip()
                if len(content) > 300:
                    snippet += "..."
                lines.append(f"   {snippet}")
            if url:
                lines.append(f"   Fuente: {url}")
            lines.append("")
        return "\n".join(lines).strip() if lines else "No se encontraron resultados relevantes."

    # DuckDuckGo returns a list of dicts
    if not results:
        return "No se encontraron resultados relevantes."

    lines = []
    for i, item in enumerate(results, start=1):
        if not isinstance(item, dict):
            continue
        title = item.get("title", "Sin título")
        content = item.get("content", item.get("snippet", ""))
        url = item.get("url", item.get("link", ""))
        lines.append(f"{i}. **{title}**")
        if content:
            snippet = content[:300].rstrip()
            if len(content) > 300:
                snippet += "..."
            lines.append(f"   {snippet}")
        if url:
            lines.append(f"   Fuente: {url}")
        lines.append("")

    return "\n".join(lines).strip() if lines else "No se encontraron resultados relevantes."
