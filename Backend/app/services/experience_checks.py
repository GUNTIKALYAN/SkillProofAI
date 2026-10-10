import re
from datetime import date
from itertools import pairwise

from app.schemas.agents import JobEntry

_MONTH = re.compile(r"^(\d{4})(?:-(\d{2}))?$")
_SENIOR = {"senior", "lead", "staff", "principal"}
_AUDIT_KINDS = {"date", "unsupported"}


def check_entries(entries: list[JobEntry], today: date | None = None) -> list[dict]:
    current = today or date.today()
    flags: list[dict] = []
    spans: list[tuple[date, date, JobEntry]] = []
    for entry in entries:
        start = _month(entry.start)
        end = current if entry.end is None else _month(entry.end)
        if start is None or end is None:
            flags.append(_flag("date", f"Could not read the dates for {entry.company}."))
            continue
        if start > current or (entry.end is not None and end > current):
            flags.append(_flag("date", f"{entry.company} lists a future date."))
        if end < start:
            flags.append(_flag("date", f"{entry.company} ends before it starts."))
            continue
        spans.append((start, end, entry))
    spans.sort(key=lambda item: item[0])
    for earlier, later in pairwise(spans):
        if later[0] <= earlier[1]:
            flags.append(_flag("date", f"{earlier[2].company} overlaps {later[2].company}."))
        elif _months(earlier[1], later[0]) > 6:
            flags.append(_flag("date", f"There is a gap longer than 6 months before {later[2].company}."))
    if spans and _senior_span(spans, current):
        flags.append(_flag("date", "A senior title is listed for less than three years."))
    return flags


def audit_flags(flags: list[dict]) -> list[dict]:
    return [flag for flag in flags if flag.get("kind") in _AUDIT_KINDS]


def _senior_span(spans: list[tuple[date, date, JobEntry]], today: date) -> bool:
    titles = " ".join(item[2].title.lower() for item in spans)
    words = set(re.findall(r"[a-z]+", titles))
    if not words & _SENIOR:
        return False
    start = min(item[0] for item in spans)
    end = max(item[1] for item in spans)
    end = min(end, today)
    return _months(start, end) < 36


def _month(value: str) -> date | None:
    match = _MONTH.fullmatch(value.strip())
    if match is None:
        return None
    month = int(match.group(2) or "1")
    if month < 1 or month > 12:
        return None
    return date(int(match.group(1)), month, 1)


def _months(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + (end.month - start.month)


def _flag(kind: str, detail: str) -> dict:
    return {"kind": kind, "detail": detail}
