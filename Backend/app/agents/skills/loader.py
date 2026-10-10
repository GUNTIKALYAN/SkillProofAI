import hashlib
from dataclasses import dataclass
from pathlib import Path

_REQUIRED = ("name", "description", "tools", "inputs", "outputs", "limits")
_LIMITS = ("max_tool_calls", "timeout_s")


class SkillError(Exception):
    pass


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    tools: tuple[str, ...]
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    limits: dict[str, int]
    body: str
    digest: bytes


def load_skills(root: Path | None = None) -> dict[str, Skill]:
    base = root or Path(__file__).resolve().parent
    found: dict[str, Skill] = {}
    for path in sorted(base.glob("*/SKILL.md")):
        skill = _read_skill(path)
        if skill.name != path.parent.name:
            raise SkillError(f"{skill.name} does not match its folder")
        found[skill.name] = skill
    if not found:
        raise SkillError("No skill files were found")
    return found


def skill_hash(skills: dict[str, Skill]) -> str:
    digest = hashlib.sha256()
    for name in sorted(skills):
        digest.update(skills[name].digest)
    return digest.hexdigest()


def allowlist(skills: dict[str, Skill]) -> dict[str, set[tuple[str, str]]]:
    parsed: dict[str, set[tuple[str, str]]] = {}
    for name, skill in skills.items():
        parsed[name] = {_split_tool(item) for item in skill.tools}
    return parsed


def require_listed_tools(skills: dict[str, Skill], catalog: dict[str, set[str]]) -> None:
    for skill in skills.values():
        for item in skill.tools:
            server, tool = _split_tool(item)
            if tool not in catalog.get(server, set()):
                raise SkillError(f"{skill.name} lists unknown tool {item}")


def _read_skill(path: Path) -> Skill:
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    front, body = _split_front(text, path.name)
    _check_front(front, path.name)
    if not body:
        raise SkillError(f"{path.name} is missing a body")
    limits = front["limits"]
    return Skill(
        name=str(front["name"]),
        description=str(front["description"]),
        tools=tuple(front["tools"]),
        inputs=tuple(front["inputs"]),
        outputs=tuple(front["outputs"]),
        limits={key: int(limits[key]) for key in _LIMITS},
        body=body,
        digest=hashlib.sha256(raw).digest(),
    )


def _split_front(text: str, label: str) -> tuple[dict[str, object], str]:
    if not text.startswith("---"):
        raise SkillError(f"{label} is missing front matter")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise SkillError(f"{label} is missing front matter")
    return _parse_front(parts[1]), parts[2].strip()


def _parse_front(block: str) -> dict[str, object]:
    data: dict[str, object] = {}
    key: str | None = None
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if line.startswith("  ") and ":" in stripped and key == "limits" and isinstance(data.get(key), dict):
            name, value = stripped.split(":", 1)
            data[key][name.strip()] = int(value.strip())
            continue
        if stripped.startswith("- ") and key and isinstance(data.get(key), list):
            data[key].append(stripped[2:].strip())
            continue
        name, value = stripped.split(":", 1)
        key = name.strip()
        raw = value.strip()
        if key == "limits":
            data[key] = {}
        elif raw in {"", "[]"}:
            data[key] = []
        else:
            data[key] = raw
    return data


def _check_front(front: dict[str, object], label: str) -> None:
    missing = [key for key in _REQUIRED if key not in front]
    if missing:
        raise SkillError(f"{label} is missing {', '.join(missing)}")
    limits = front["limits"]
    if not isinstance(limits, dict) or any(key not in limits for key in _LIMITS):
        raise SkillError(f"{label} has incomplete limits")
    for item in front["tools"]:
        _split_tool(str(item))


def _split_tool(item: str) -> tuple[str, str]:
    server, separator, tool = item.partition(".")
    if not separator or not server or not tool or "." in tool:
        raise SkillError(f"Tool {item} must be server.tool")
    return server, tool
