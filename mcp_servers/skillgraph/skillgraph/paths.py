from collections import deque
from dataclasses import dataclass

from skillgraph.ontology import Edge

MAX_HOPS = 3
REVERSE_PART_OF = 0.4


@dataclass(frozen=True)
class Hop:
    relation: str
    source: str
    target: str
    weight: float
    forward: bool


def adjacency(edges: list[Edge]) -> dict[str, list[Hop]]:
    graph: dict[str, list[Hop]] = {}
    for edge in edges:
        _add(graph, Hop(edge.relation, edge.source, edge.target, edge.weight, True))
        if edge.relation == "RELATED_TO":
            _add(graph, Hop(edge.relation, edge.target, edge.source, edge.weight, True))
        elif edge.relation == "PART_OF":
            _add(graph, Hop("PART_OF", edge.target, edge.source, REVERSE_PART_OF, False))
    for hops in graph.values():
        hops.sort(key=lambda hop: (hop.target, hop.relation, hop.forward))
    return graph


def best_path(graph: dict[str, list[Hop]], source: str, target: str) -> tuple[Hop, ...] | None:
    if source == target:
        return None
    best: tuple[tuple[float, int, str], tuple[Hop, ...]] | None = None
    queue: deque[tuple[str, tuple[Hop, ...]]] = deque([(source, ())])
    while queue:
        node, path = queue.popleft()
        if len(path) >= MAX_HOPS:
            continue
        seen = {source, *(hop.target for hop in path)}
        for hop in graph.get(node, []):
            if hop.target in seen:
                continue
            new_path = path + (hop,)
            if hop.target == target:
                points = min(item.weight for item in new_path)
                signature = " ".join(f"{item.relation}:{item.target}" for item in new_path)
                rank = (-points, len(new_path), signature)
                if best is None or rank < best[0]:
                    best = (rank, new_path)
                continue
            queue.append((hop.target, new_path))
    if best is None:
        return None
    return best[1]


def path_reason(start: str, path: tuple[Hop, ...]) -> str:
    parts = [start]
    for hop in path:
        if hop.forward:
            parts.append(f"{hop.relation} {hop.target}")
        else:
            parts.append(f"is broader than {hop.target}")
    return " ".join(parts)


def ancestors(edges: list[Edge], canonical: str) -> list[str]:
    found: list[str] = []
    seen = {canonical}
    stack = [canonical]
    while stack:
        node = stack.pop()
        for edge in edges:
            if edge.source != node or edge.relation != "PART_OF" or edge.target in seen:
                continue
            seen.add(edge.target)
            found.append(edge.target)
            stack.append(edge.target)
    return sorted(found)


def _add(graph: dict[str, list[Hop]], hop: Hop) -> None:
    graph.setdefault(hop.source, []).append(hop)
