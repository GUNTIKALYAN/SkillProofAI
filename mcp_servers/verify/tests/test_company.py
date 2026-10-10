import pytest

from verifymcp.company import classify, company_query


def test_company_query_is_the_name_only() -> None:
    assert company_query("  Acme   Corp ") == "Acme Corp"


def test_company_query_rejects_a_blank_name() -> None:
    with pytest.raises(ValueError):
        company_query("   ")


def test_classify_never_uses_a_fake_status() -> None:
    assert classify(None) == ("skipped", 0.0)
    assert classify(0) == ("not_found", 0.3)
    assert classify(1) == ("ambiguous", 0.4)
    assert classify(3) == ("found", 0.6)
    assert "fake" not in {item[0] for item in (classify(None), classify(0), classify(1), classify(3))}
