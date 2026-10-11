def normalize_text(text: str) -> str:
    """
    Normalizes text for comparison.
    """
    return text.lower().strip()


def is_header(line: str, headers: list[str]) -> bool:
    """
    Checks if a line matches any known header.
    """
    return any(line.startswith(h) for h in headers)


def contains_any(text: str, keywords: set[str]) -> bool:
    """
    Returns True if any keyword appears in text.
    """
    return any(keyword in text for keyword in keywords)
