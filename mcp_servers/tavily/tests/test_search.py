from tavilymcp.search import parse_results, search_body


def test_parse_results_keeps_short_fields() -> None:
    body = parse_results(
        {
            "results": [
                {"title": "Docs", "url": "https://example.com", "content": "x" * 500},
            ]
        }
    )
    assert body["results"][0]["title"] == "Docs"
    assert len(body["results"][0]["content"]) == 400


def test_search_body_uses_the_query_only() -> None:
    body = search_body("Docker", "secret")
    assert body["query"] == "Docker"
    assert "resume" not in body["query"]
