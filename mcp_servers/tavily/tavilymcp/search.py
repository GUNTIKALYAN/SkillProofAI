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
