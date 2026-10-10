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
