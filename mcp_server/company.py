import logging

import httpx

logger = logging.getLogger(__name__)

COMPANY_TIMEOUT = 15.0


def company_query(name: str) -> str:
    cleaned = " ".join(name.split())
    if not cleaned or len(cleaned) > 120:
        raise ValueError("company name is invalid")
    return cleaned


def classify(count: int | None) -> tuple[str, float]:
    if count is None:
        return "skipped", 0.0
    if count <= 0:
        return "not_found", 0.3
    if count == 1:
        return "ambiguous", 0.4
    return "found", 0.6


def check_company(name: str, api_key: str) -> dict:
    try:
        query = company_query(name)
    except ValueError:
        return {"status": "skipped", "confidence": 0.0}
    status, confidence = classify(_result_count(api_key, query))
    logger.info("company check status=%s", status)
    return {"status": status, "confidence": confidence}


def _result_count(api_key: str, query: str) -> int | None:
    try:
        response = httpx.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": query,
                "max_results": 3,
                "search_depth": "basic",
                "include_answer": False,
            },
            timeout=COMPANY_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        logger.error("company search failed")
        return None
    if not isinstance(payload, dict):
        return None
    results = payload.get("results")
    if not isinstance(results, list):
        return 0
    return len(results)
