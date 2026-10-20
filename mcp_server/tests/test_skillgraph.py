from seed_data import MemoryStore, load_document
from skillgraph import (
    RESOLVE,
    audit_skills,
    canonicalize,
    explain_skill,
    related_skills,
    score_match,
    what_if_learn,
)

JD = [
    ("Machine Learning", "required"),
    ("Python", "required"),
    ("Docker", "preferred"),
]
CANDIDATES = ["numpy", "pandas", "fastapi"]


def _store() -> MemoryStore:
    return MemoryStore(load_document())


def test_numpy_and_pandas_resolve_under_machine_learning() -> None:
    store = _store()
    numpy = canonicalize(store, "numpy")
    pandas = canonicalize(store, "pandas")

    assert numpy.canonical == "NumPy"
    assert pandas.canonical == "pandas"
    assert "Machine Learning" in numpy.ancestors
    assert "Machine Learning" in pandas.ancestors


def test_golden_score_is_stable_and_explained() -> None:
    store = _store()
    first = score_match(store, JD, CANDIDATES)
    second = score_match(store, JD, CANDIDATES)

    assert first == second
    assert first.label == "JD Match Score"
    assert first.score == 0.52
    by_skill = {item.skill: item for item in first.breakdown}
    assert by_skill["Machine Learning"].kind == "neighbour"
    assert by_skill["Machine Learning"].points == 0.6
    assert "PART_OF Machine Learning" in by_skill["Machine Learning"].reason
    assert by_skill["Python"].kind == "neighbour"
    assert by_skill["Python"].points == 0.7
    assert "IMPLIES Python" in by_skill["Python"].reason
    assert by_skill["Docker"].kind == "missing"
    assert by_skill["Docker"].points == 0.0


def test_alias_scores_as_exact_value() -> None:
    result = score_match(_store(), [("scikit-learn", "required")], ["sklearn"])

    assert result.score == 1.0
    assert result.breakdown[0].kind == "alias"
    assert result.breakdown[0].reason == "alias of scikit-learn"


def test_required_skill_weighs_more_than_preferred() -> None:
    store = _store()
    jobs = [("Python", "required"), ("Docker", "preferred")]
    missing_required = score_match(store, jobs, ["Docker"])
    missing_preferred = score_match(store, jobs, ["Python"])

    assert missing_preferred.score > missing_required.score


def test_audit_and_what_if_follow_the_score() -> None:
    store = _store()
    audit = audit_skills(store, JD, CANDIDATES)
    statuses = {item.skill: item.status for item in audit.items}
    learned = what_if_learn(store, "Docker", CANDIDATES, JD)

    assert statuses == {
        "Machine Learning": "partial",
        "Python": "partial",
        "Docker": "missing",
    }
    assert learned.before == 0.52
    assert learned.after == 0.72
    assert learned.delta == 0.2
    assert learned.known is True


def test_explain_and_related_skills() -> None:
    store = _store()
    explained = explain_skill(store, "numpy")
    related = related_skills(store, "FastAPI")
    names = {item.skill for item in related.related}

    assert explained.known is True
    assert explained.canonical == "NumPy"
    assert explained.match == "exact"
    assert "Machine Learning" in explained.ancestors
    assert "Python" in names
    assert "REST" in names


def test_cypher_reads_are_parameterised() -> None:
    assert "$key" in RESOLVE
    assert "f'" not in RESOLVE
    assert ".format(" not in RESOLVE
