import logging
from typing import Optional

import requests
from open_webui.retrieval.web.main import SearchResult, get_filtered_results
from open_webui.env import SRC_LOG_LEVELS

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["RAG"])


def search_kagi(
    api_key: str, query: str, count: int, filter_list: Optional[list[str]] = None
) -> list[SearchResult]:
    """
    Search using Kagi's Search API and return the results as a list of SearchResult objects.
    
    The Search API will inherit the settings in your account, including results personalization and snippet length.
    
    Args:
        api_key (str): A Kagi Search API key for authentication
        query (str): The search query to perform
        count (int): Maximum number of search results to retrieve
        filter_list (Optional[list[str]], optional): List of strings to filter search results. Defaults to None.
    
    Returns:
        list[SearchResult]: A list of search results matching the query, filtered and processed
    
    Raises:
        requests.HTTPError: If the API request fails or returns an error status code
    
    Example:
        >>> results = search_kagi("your_api_key", "python programming", 5)
        >>> for result in results:
        ...     print(result.title)
    """
    url = "https://kagi.com/api/v0/search"
    headers = {
        "Authorization": f"Bot {api_key}",
    }
    params = {"q": query, "limit": count}

    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    json_response = response.json()
    search_results = json_response.get("data", [])

    results = [
        SearchResult(
            link=result["url"], title=result["title"], snippet=result.get("snippet")
        )
        for result in search_results
        if result["t"] == 0
    ]

    print(results)

    if filter_list:
        results = get_filtered_results(results, filter_list)

    return results
