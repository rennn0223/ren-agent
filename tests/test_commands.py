# tests/test_commands.py

import asyncio

from ren_agent.core.commands import (
    CommandContext,
    get_command,
    register_builtin_commands,
)
from ren_agent.core.skills import register_skill, Skill


class DummyCtx(CommandContext):
    def __init__(self) -> None:
        self.user = []
        self.assistant = []
        self.system = []
        self.asked = []
        self.exited = False
        self.skills_log = []

    async def write_user(self, text: str) -> None:
        self.user.append(text)

    async def write_assistant(self, text: str) -> None:
        self.assistant.append(text)

    def write_system(self, text: str) -> None:
        self.system.append(text)

    async def ask_llm(self, prompt: str) -> None:
        self.asked.append(prompt)

    def exit_app(self) -> None:
        self.exited = True

    async def run_skill(self, name: str, **kwargs) -> None:
        self.skills_log.append((name, kwargs))


def test_builtin_commands_register() -> None:
    register_builtin_commands()
    assert get_command("help") is not None
    assert get_command("q") is not None
    assert get_command("model") is not None


def test_q_command_calls_llm() -> None:
    register_builtin_commands()
    cmd = get_command("q")
    assert cmd is not None

    ctx = DummyCtx()
    asyncio.run(cmd.handler(ctx, "幫我寫一個 ROS2 範例"))
    assert ctx.asked == ["幫我寫一個 ROS2 範例"]