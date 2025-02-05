import logging
import os
from pprint import pprint
from typing import Optional
import requests
from open_webui.retrieval.web.main import SearchResult, get_filtered_results
from open_webui.env import SRC_LOG_LEVELS
import argparse

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["RAG"])
"""
Documentation: https://docs.microsoft.com/en-us/bing/search-apis/bing-web-search/overview
"""


def search_bing(
    subscription_key: str,
    endpoint: str,
    locale: str,
    query: str,
    count: int,
    filter_list: Optional[list[str]] = None,
) -> list[SearchResult]:
    """
    Perform a Bing web search using the Bing Search API.
    
    This function sends an HTTP GET request to the specified Bing API endpoint with the provided
    subscription key, search query, and locale (market) information. It parses the JSON response 
    to extract web page results, optionally filters these results using a supplied filter list, and 
    converts the results into a list of SearchResult objects.
    
    Parameters:
        subscription_key (str): The API key for authenticating with the Bing Search API.
        endpoint (str): The URL endpoint for the Bing Search API.
        locale (str): The locale (market) to be used in the search request.
        query (str): The search query string.
        count (int): The number of search results to retrieve.
        filter_list (Optional[list[str]], optional): A list of strings used to filter the results.
            If provided, only results matching the filters will be returned. Defaults to None.
    
    Returns:
        list[SearchResult]: A list of SearchResult objects, each containing the URL, title, and snippet from the search results.
    
    Raises:
        Exception: Any exception raised during the HTTP request or response processing is logged and re-raised.
    """
    mkt = locale
    params = {"q": query, "mkt": mkt, "count": count}
    headers = {"Ocp-Apim-Subscription-Key": subscription_key}

    try:
        response = requests.get(endpoint, headers=headers, params=params)
        response.raise_for_status()
        json_response = response.json()
        results = json_response.get("webPages", {}).get("value", [])
        if filter_list:
            results = get_filtered_results(results, filter_list)
        return [
            SearchResult(
                link=result["url"],
                title=result.get("name"),
                snippet=result.get("snippet"),
            )
            for result in results
        ]
    except Exception as ex:
        log.error(f"Error: {ex}")
        raise ex


def main():
    parser = argparse.ArgumentParser(description="Search Bing from the command line.")
    parser.add_argument(
        "query",
        type=str,
        default="Top 10 international news today",
        help="The search query.",
    )
    parser.add_argument(
        "--count", type=int, default=10, help="Number of search results to return."
    )
    parser.add_argument(
        "--filter", nargs="*", help="List of filters to apply to the search results."
    )
    parser.add_argument(
        "--locale",
        type=str,
        default="en-US",
        help="The locale to use for the search, maps to market in api",
    )

    args = parser.parse_args()

    results = search_bing(args.locale, args.query, args.count, args.filter)
    pprint(results)
