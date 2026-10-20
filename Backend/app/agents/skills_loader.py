import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

_LIMITS = ("max_tool_calls", "timeout_s")
_HEADING = re.compile(r"^## ([a-z_]+)\s*$")


class SkillError(Exception):
    pass


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    tools: tuple[str, ...]
    limits: dict[str, int]
    body: str
    digest: bytes
    file_hash: str


def load_skills(path: Path | None = None) -> dict[str, Skill]:
    file = path or Path(__file__).resolve().parent / "skills.md"
    text = file.read_text(encoding="utf-8")
    file_hash = hashlib.sha256(file.read_bytes()).hexdigest()
    found: dict[str, Skill] = {}
    for name, block in _sections(text):
        if name in found:
            raise SkillError(f"{name} is listed twice")
        found[name] = _skill(name, block, file_hash)
    if not found:
        raise SkillError("No skill sections were found")
    return found


def skill_hash(skills: dict[str, Skill]) -> str:
    if not skills:
        raise SkillError("No skill sections were found")
    hashes = {skill.file_hash for skill in skills.values()}
    if len(hashes) != 1:
        raise SkillError("Skill sections do not share one file hash")
    return hashes.pop()


def allowlist(skills: dict[str, Skill]) -> dict[str, set[str]]:
    return {name: set(skill.tools) for name, skill in skills.items()}


def require_listed_tools(skills: dict[str, Skill], known: set[str]) -> None:
    for skill in skills.values():
        missing = [tool for tool in skill.tools if tool not in known]
        if missing:
            names = ", ".join(missing)
            raise SkillError(f"{skill.name} lists unknown tool {names}")


def _sections(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    name: str | None = None
    lines: list[str] = []
    for line in text.splitlines():
        match = _HEADING.match(line)
        if match:
            if name is not None:
                sections.append((name, "\n".join(lines).strip()))
            name = match.group(1)
            lines = []
            continue
        if name is not None:
            lines.append(line)
    if name is not None:
        sections.append((name, "\n".join(lines).strip()))
    return sections


def _skill(name: str, block: str, file_hash: str) -> Skill:
    description = ""
    tools: list[str] = []
    limits: dict[str, int] = {}
    rules: list[str] = []
    in_rules = False
    for line in block.splitlines():
        if line.startswith("description:"):
            description = line.split(":", 1)[1].strip()
            in_rules = False
        elif line.startswith("tools:"):
            tools = _tools(line.split(":", 1)[1])
            in_rules = False
        elif line.startswith("limits:"):
            limits = _limits(line.split(":", 1)[1])
            in_rules = False
        elif line.startswith("rules:"):
            in_rules = True
            rest = line.split(":", 1)[1].strip()
            if rest:
                rules.append(rest)
        elif in_rules:
            rules.append(line)
        elif line.strip():
            raise SkillError(f"{name} has an unknown line")
    if not description:
        raise SkillError(f"{name} is missing a description")
    if any(key not in limits for key in _LIMITS):
        raise SkillError(f"{name} has incomplete limits")
    body = "\n".join(rules).strip()
    if not body:
        raise SkillError(f"{name} is missing rules")
    digest = hashlib.sha256(block.encode("utf-8")).digest()
    return Skill(name, description, tuple(tools), limits, body, digest, file_hash)


def _tools(raw: str) -> list[str]:
    tools = [item.strip() for item in raw.split(",") if item.strip()]
    for tool in tools:
        if not tool.replace("_", "").isalnum() or tool != tool.lower():
            raise SkillError(f"Tool {tool} must be a plain tool name")
    return tools


def _limits(raw: str) -> dict[str, int]:
    limits: dict[str, int] = {}
    for part in raw.split(","):
        if not part.strip():
            continue
        key, value = part.split("=", 1)
        limits[key.strip()] = int(value.strip())
    return limits
