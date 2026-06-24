from __future__ import annotations

import asyncio

from ren_agent.core.skills import Skill, register_skill, run_skill


def test_run_skill_passes_name_kwarg_without_collision() -> None:
    """
    迴歸測試：skill 自身有名為 `name` 的參數時，
    run_skill("goto", name=...) 不能再丟
    'got multiple values for argument name'。
    """

    async def fake_goto(name: str) -> str:
        return f"goto:{name}"

    register_skill(Skill("goto_test", "demo", fake_goto))

    result = asyncio.run(run_skill("goto_test", name="機械系館"))
    assert result == "goto:機械系館"


def test_run_skill_other_kwargs() -> None:
    async def fake_drive(direction: str, speed: float) -> str:
        return f"{direction}@{speed}"

    register_skill(Skill("drive_test", "demo", fake_drive))

    result = asyncio.run(run_skill("drive_test", direction="forward", speed=0.3))
    assert result == "forward@0.3"
