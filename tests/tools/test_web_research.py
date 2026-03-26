# tests/tools/test_web_research.py
import os
import sys
import pytest
import asyncio
from dotenv import load_dotenv
from unittest.mock import patch, MagicMock

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'src')))

from tools.web_research import concise_search

@pytest.mark.asyncio
@patch('tools.web_research.serpapi.Client')
async def test_web_research_tool(mock_serpapi_client):
    # Mock the search results
    mock_search = MagicMock()
    mock_search.search.return_value = {
        "organic_results": [
            {
                "title": "Apple Watch Series 9",
                "link": "https://www.apple.com/apple-watch-series-9/",
                "snippet": "The Apple Watch Series 9 features a new S9 SiP, a brighter display, and Double Tap."
            }
        ]
    }
    mock_serpapi_client.return_value = mock_search
    
    load_dotenv()
    print("--- Testing Web Research Tool ---")
    
    search_results = await concise_search.ainvoke({"query": "What are the key features of the Apple Watch Series 9?"})
    print(search_results)
    assert "error" not in search_results.lower()
    assert "Apple Watch" in search_results