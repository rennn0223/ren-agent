from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List

SkillFunc = Callable[..., Awaitable[str]]


@dataclass
class Skill:
    name: str
    description: str
    func: SkillFunc
    tool_schema: dict | None = field(default=None)
    """OpenAI / Ollama 風格的 function-tool schema。設為 None 表示這個 skill
    不公開給 LLM 使用（只能被 slash command 內部呼叫）。"""


_SKILLS: Dict[str, Skill] = {}


def register_skill(skill: Skill) -> None:
    _SKILLS[skill.name] = skill


def get_skill(name: str) -> Skill | None:
    return _SKILLS.get(name)


def all_skills() -> List[Skill]:
    return list(_SKILLS.values())


def all_tools() -> List[dict]:
    """回傳所有有 tool_schema 的 skill，包成 Ollama tools 格式。"""
    tools = []
    for s in _SKILLS.values():
        if s.tool_schema:
            tools.append(s.tool_schema)
    return tools


async def run_skill(name: str, **kwargs: Any) -> str:
    skill = _SKILLS.get(name)
    if not skill:
        raise KeyError(f"Skill not found: {name}")
    return await skill.func(**kwargs)
