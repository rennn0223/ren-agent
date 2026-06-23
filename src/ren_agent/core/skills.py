"""
Skill registry — 所有「會做事」的 async 函式都註冊在這裡。

兩種使用方式：
  1. 被 slash command 呼叫：ctx.run_skill("drive", direction="forward")
  2. 被 LLM tool calling 呼叫：OllamaAgent 從 all_tools() 抓 schema，
     LLM 決定要 call 哪個 → 反查 _SKILLS → 執行

Skill 的 tool_schema 是選用的。沒填 = 只能被 slash command 用，
LLM 看不到（適合 internal 的 /clear、/help 這類）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List

# Skill 函式型別：任何 keyword args → 回字串（給人看的結果）
SkillFunc = Callable[..., Awaitable[str]]


@dataclass
class Skill:
    """單一 skill 的定義。"""

    name: str
    description: str
    func: SkillFunc
    # OpenAI / Ollama 風格的 function-tool schema
    # 設 None 表示這個 skill 不公開給 LLM（只能被 slash command 內部呼叫）
    tool_schema: dict | None = field(default=None)


# ── Registry（模組級單例 dict）────────────────────────
_SKILLS: Dict[str, Skill] = {}


def register_skill(skill: Skill) -> None:
    """註冊（或覆寫）一個 skill。"""
    _SKILLS[skill.name] = skill


def get_skill(name: str) -> Skill | None:
    """依名稱取得 skill；找不到回 None。"""
    return _SKILLS.get(name)


def all_skills() -> List[Skill]:
    """所有已註冊的 skill。"""
    return list(_SKILLS.values())


def all_tools() -> List[dict]:
    """
    回傳所有有 tool_schema 的 skill，包成 Ollama tools 格式。
    OllamaAgent.chat_stream(tools=...) 直接吃這個。
    """
    return [s.tool_schema for s in _SKILLS.values() if s.tool_schema]


async def run_skill(name: str, **kwargs: Any) -> str:
    """執行指定 skill；找不到會拋 KeyError。"""
    skill = _SKILLS.get(name)
    if not skill:
        raise KeyError(f"Skill not found: {name}")
    return await skill.func(**kwargs)
