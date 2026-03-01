"""Tests for klaus.search -- Tavily web search integration."""

from unittest.mock import MagicMock, patch

import pytest

from klaus.search import WebSearch, TOOL_DEFINITION


class TestToolDefinition:
    def test_has_required_fields(self):
        assert TOOL_DEFINITION["name"] == "web_search"
        assert "input_schema" in TOOL_DEFINITION
        assert "query" in TOOL_DEFINITION["input_schema"]["properties"]
        assert "query" in TOOL_DEFINITION["input_schema"]["required"]


class TestWebSearch:
    @patch("klaus.search.TavilyClient")
    def test_search_with_results(self, mock_tavily_cls):
        mock_client = MagicMock()
        mock_tavily_cls.return_value = mock_client
        mock_client.search.return_value = {
            "results": [
                {
                    "title": "P-value explained",
                    "url": "https://example.com/pvalue",
                    "content": "A p-value is the probability...",
                },
                {
                    "title": "Statistics basics",
                    "url": "https://example.com/stats",
                    "content": "Statistics is the study of...",
                },
            ]
        }

        ws = WebSearch()
        result = ws.search("what is a p-value")

        assert "P-value explained" in result
        assert "https://example.com/pvalue" in result
        assert "Statistics basics" in result
        mock_client.search.assert_called_once_with(
            query="what is a p-value",
            max_results=5,
            search_depth="advanced",
        )

    @patch("klaus.search.TavilyClient")
    def test_search_no_results(self, mock_tavily_cls):
        mock_client = MagicMock()
        mock_tavily_cls.return_value = mock_client
        mock_client.search.return_value = {"results": []}

        ws = WebSearch()
        result = ws.search("something obscure")
        assert result == "No results found."

    @patch("klaus.search.TavilyClient")
    def test_search_api_error(self, mock_tavily_cls):
        mock_client = MagicMock()
        mock_tavily_cls.return_value = mock_client
        mock_client.search.side_effect = Exception("API rate limit")

        ws = WebSearch()
        result = ws.search("test query")
        assert "Search failed" in result
        assert "API rate limit" in result

    @patch("klaus.search.TavilyClient")
    def test_search_custom_max_results(self, mock_tavily_cls):
        mock_client = MagicMock()
        mock_tavily_cls.return_value = mock_client
        mock_client.search.return_value = {"results": []}

        ws = WebSearch()
        ws.search("test", max_results=3)

        mock_client.search.assert_called_once_with(
            query="test", max_results=3, search_depth="advanced"
        )

    @patch("klaus.search.TavilyClient")
    def test_search_result_formatting(self, mock_tavily_cls):
        mock_client = MagicMock()
        mock_tavily_cls.return_value = mock_client
        mock_client.search.return_value = {
            "results": [
                {"title": "A", "url": "http://a.com", "content": "Content A"},
                {"title": "B", "url": "http://b.com", "content": "Content B"},
            ]
        }

        ws = WebSearch()
        result = ws.search("test")

        assert "---" in result
        assert "**A**" in result
        assert "**B**" in result
