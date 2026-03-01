import logging

from tavily import TavilyClient

from klaus.config import TAVILY_API_KEY

logger = logging.getLogger(__name__)

TOOL_DEFINITION = {
    "name": "web_search",
    "description": (
        "Search the web to verify claims, look up referenced papers or authors, "
        "check definitions, or find additional context. Use this whenever your "
        "own knowledge is insufficient or uncertain."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query",
            }
        },
        "required": ["query"],
    },
}


class WebSearch:
    """Wraps Tavily search for use as a Claude tool."""

    def __init__(self):
        self._client = TavilyClient(api_key=TAVILY_API_KEY)

    def search(self, query: str, max_results: int = 5) -> str:
        """Run a search and return formatted results as a string for Claude."""
        logger.info("Tavily search: '%s'", query)
        try:
            response = self._client.search(
                query=query,
                max_results=max_results,
                search_depth="advanced",
            )
        except Exception as e:
            logger.error("Tavily search failed: %s", e)
            return f"Search failed: {e}"

        results = response.get("results", [])
        if not results:
            logger.info("Tavily search returned 0 results")
            return "No results found."

        logger.info("Tavily search returned %d results", len(results))

        formatted: list[str] = []
        for r in results:
            title = r.get("title", "No title")
            url = r.get("url", "")
            content = r.get("content", "")
            formatted.append(f"**{title}**\n{url}\n{content}")

        return "\n\n---\n\n".join(formatted)
