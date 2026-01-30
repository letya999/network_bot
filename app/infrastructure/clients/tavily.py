"""Tavily API client for OSINT searches."""
import logging
from typing import Dict, Any, List, Optional
import aiohttp
from app.config.constants import TAVILY_MAX_RESULTS, TAVILY_SEARCH_DEPTH, TAVILY_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


class TavilyClient:
    """Client for interacting with Tavily AI Search API."""

    def __init__(self, api_key: str):
        """
        Initialize Tavily client.

        Args:
            api_key: Tavily API key
        """
        self.api_key = api_key
        self.base_url = "https://api.tavily.com"

    async def search(
        self,
        query: str,
        include_domains: Optional[List[str]] = None,
        max_results: int = TAVILY_MAX_RESULTS,
        search_depth: str = TAVILY_SEARCH_DEPTH
    ) -> List[Dict[str, Any]]:
        """
        Perform a search using Tavily AI API.

        Args:
            query: Search query
            include_domains: Optional list of domains to limit search to
            max_results: Maximum number of results to return
            search_depth: Search depth ("basic" or "advanced")

        Returns:
            List of search results with content
        """
        if not self.api_key:
            logger.warning("Tavily API key not configured")
            return []

        url = f"{self.base_url}/search"
        payload = {
            "api_key": self.api_key,
            "query": query,
            "search_depth": search_depth,
            "include_answer": False,
            "include_raw_content": False,
            "max_results": max_results,
        }

        if include_domains:
            payload["include_domains"] = include_domains

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=TAVILY_TIMEOUT_SECONDS)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Tavily API error {response.status}: {error_text}")
                        return []

                    data = await response.json()
                    return data.get("results", [])

        except aiohttp.ClientError as e:
            logger.error(f"Tavily API network error: {e}")
            return []
        except Exception as e:
            logger.exception(f"Unexpected error in Tavily search: {e}")
            return []
