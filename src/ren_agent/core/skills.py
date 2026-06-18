from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict

SkillFunc = Callable[..., Awaitable[str]]


@dataclass
class Skill:
    name: str
    description: str
    func: SkillFunc


_SKILLS: Dict[str, Skill] = {}


def register_skill(skill: Skill) -> None:
    _SKILLS[skill.name] = skill


def get_skill(name: str) -> Skill | None:
    return _SKILLS.get(name)


async def run_skill(name: str, **kwargs: Any) -> str:
    skill = _SKILLS.get(name)
    if not skill:
        raise KeyError(f"Skill not found: {name}")
    return await skill.func(**kwargs)
