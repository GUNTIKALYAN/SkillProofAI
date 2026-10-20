import logging

import httpx

logger = logging.getLogger(__name__)

SEARCH_TIMEOUT = 15.0


def parse_results(body: dict) -> dict:
    results = []
    for item in (body.get("results") or [])[:5]:
        if not isinstance(item, dict):
            continue
        results.append(
            {
                "title": str(item.get("title") or "")[:200],
                "url": str(item.get("url") or "")[:300],
                "content": str(item.get("content") or "")[:400],
            }
        )
    return {"results": results}


def search_body(query: str, api_key: str) -> dict:
    return {
        "api_key": api_key,
        "query": query,
        "max_results": 5,
        "search_depth": "basic",
        "include_answer": False,
    }


def tavily_search(query: str, api_key: str) -> dict:
    cleaned = " ".join(query.split())
    if not cleaned or len(cleaned) > 200:
        return {"results": []}
    try:
        response = httpx.post(
            "https://api.tavily.com/search",
            json=search_body(cleaned, api_key),
            timeout=SEARCH_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.error("tavily search failed error=%s", type(exc).__name__)
        return {"results": []}
    if not isinstance(payload, dict):
        return {"results": []}
    found = parse_results(payload)
    logger.info("tavily search results=%s", len(found["results"]))
    return found
