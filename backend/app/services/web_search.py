"""
Web search service — finds relevant information online.

Supports multiple providers:
- duckduckgo: Free, no API key. May not work in all regions (blocked in China).
- bing:     Bing Search API via Azure. Requires BING_SEARCH_API_KEY in .env.
            Get a key: https://portal.azure.com -> Cognitive Services
            Free tier: 1000 queries/month.

The active provider is selected by the WEB_SEARCH_PROVIDER setting.
"""

import urllib.parse
from typing import Optional

import httpx

from app.core.config import settings


class WebSearchResult:
    """A single web search result."""

    def __init__(self, title: str, url: str, snippet: str):
        self.title = title
        self.url = url
        self.snippet = snippet


class WebSearchService:
    """Search the web for relevant information."""

    @staticmethod
    def search(query: str, max_results: int = 5) -> list[WebSearchResult]:
        """Search using the configured provider."""
        provider = settings.WEB_SEARCH_PROVIDER

        if provider == "bing":
            if settings.BING_SEARCH_API_KEY:
                return WebSearchService._search_bing_api(query, max_results)
            # Fall through to duckduckgo if no API key

        # Default: DuckDuckGo
        results = WebSearchService._search_duckduckgo(query, max_results)
        if results:
            return results

        # Fallback: try Bing API even if not configured as primary
        if settings.BING_SEARCH_API_KEY:
            return WebSearchService._search_bing_api(query, max_results)

        return results  # empty list

    @staticmethod
    def _search_duckduckgo(query: str, max_results: int) -> list[WebSearchResult]:
        """Search using DuckDuckGo."""
        results: list[WebSearchResult] = []
        try:
            import ddgs as duckduckgo
            with duckduckgo.DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    results.append(WebSearchResult(
                        title=r.get("title", ""),
                        url=r.get("href", ""),
                        snippet=r.get("body", ""),
                    ))
        except Exception:
            pass
        return results

    @staticmethod
    def _search_bing_api(query: str, max_results: int) -> list[WebSearchResult]:
        """Search using the Bing Search API v7."""
        results: list[WebSearchResult] = []
        try:
            url = "https://api.bing.microsoft.com/v7.0/search"
            headers = {"Ocp-Apim-Subscription-Key": settings.BING_SEARCH_API_KEY}
            params = {"q": query, "count": max_results, "mkt": "zh-CN"}

            resp = httpx.get(url, headers=headers, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("webPages", {}).get("value", []):
                results.append(WebSearchResult(
                    title=item.get("name", ""),
                    url=item.get("url", ""),
                    snippet=item.get("snippet", ""),
                ))
        except Exception:
            pass
        return results
