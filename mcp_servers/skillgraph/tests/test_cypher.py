from skillgraph.cypher import ALIASES, EDGES, MERGE_SKILL, RESOLVE
from skillgraph.seed import seed
from skillgraph.store import Neo4jStore
from typing_extensions import Self


class _Result:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def data(self) -> list[dict]:
        return self._rows


class _Session:
    def __init__(self, rows: dict[str, list[dict]] | None = None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self._rows = rows or {}

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> bool:
        return False

    def run(self, query: str, **params: object) -> _Result:
        self.calls.append((query, params))
        return _Result(self._rows.get(query, []))


class _Driver:
    def __init__(self, session: _Session) -> None:
        self._session = session

    def session(self) -> _Session:
        return self._session


def test_seed_passes_values_as_parameters() -> None:
    session = _Session()
    count = seed(session)

    assert count > 0
    names = [params.get("name") for _query, params in session.calls]
    assert "NumPy" in names
    assert "pandas" in names
    for query, params in session.calls:
        for key, value in params.items():
            assert f"${key}" in query
            if isinstance(value, str):
                assert f"'{value}'" not in query
                assert f'"{value}"' not in query


def test_resolve_query_is_parameterised() -> None:
    session = _Session(
        {
            RESOLVE: [{"name": "NumPy", "category": "library", "kind": "alias"}],
            EDGES: [
                {
                    "source": "NumPy",
                    "relation": "PART_OF",
                    "target": "Machine Learning",
                    "weight": 0.6,
                }
            ],
            ALIASES: [{"name": "numpy"}],
        }
    )
    store = Neo4jStore(_Driver(session))  # type: ignore[arg-type]

    resolved = store.resolve("numpy")
    edges = store.edges()

    assert resolved is not None
    assert resolved.canonical == "NumPy"
    assert edges[0].target == "Machine Learning"
    resolve_query, resolve_params = session.calls[0]
    assert resolve_query == RESOLVE
    assert resolve_params == {"key": "numpy"}
    assert "numpy" not in resolve_query
    assert session.calls[1][0] == EDGES
    assert MERGE_SKILL not in {query for query, _params in session.calls}
