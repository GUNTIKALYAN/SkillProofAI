from company import classify, company_query
from github import public_repos, valid_username
from search import parse_results


def test_username_and_public_repos() -> None:
    assert valid_username(" octocat ") == "octocat"
    assert valid_username("not a user") is None
    found = public_repos(
        [
            {"name": "demo", "private": False, "language": "Python", "description": "notes"},
            {"name": "secret", "private": True, "language": "Go", "description": "hidden"},
        ]
    )
    assert found == {"repositories": [{"name": "demo", "language": "Python", "description": "notes"}]}


def test_company_status_never_says_fake() -> None:
    assert company_query("  Acme   Labs ") == "Acme Labs"
    assert classify(None) == ("skipped", 0.0)
    assert classify(0) == ("not_found", 0.3)
    assert classify(1) == ("ambiguous", 0.4)
    assert classify(3) == ("found", 0.6)
    assert "fake" not in classify(0)[0]


def test_search_results_are_clipped() -> None:
    found = parse_results({"results": [{"title": "Docs", "url": "https://example.com", "content": "notes"}]})
    assert found["results"][0]["title"] == "Docs"
