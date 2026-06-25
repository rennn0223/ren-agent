# tests/test_commands.py
import asyncio

from ren_agent.core.commands import (
    CommandContext,
    all_commands,
    get_command,
    register_builtin_commands,
)


class DummyCtx(CommandContext):
    def __init__(self) -> None:
        self.user: list[str] = []
        self.assistant: list[str] = []
        self.system: list[str] = []
        self.asked: list[str] = []
        self.exited = False
        self.skills_log: list[tuple[str, dict]] = []

    async def write_user(self, text: str) -> None:
        self.user.append(text)

    async def write_assistant(self, text: str) -> None:
        self.assistant.append(text)

    def write_system(self, text: str) -> None:
        self.system.append(text)

    def write_renderable(self, obj) -> None:
        self.system.append(repr(obj))

    async def ask_llm(self, prompt: str) -> None:
        self.asked.append(prompt)

    def exit_app(self) -> None:
        self.exited = True

    async def run_skill(self, skill: str, **kwargs) -> None:
        self.skills_log.append((skill, kwargs))


def test_builtin_commands_register() -> None:
    register_builtin_commands()
    for name in ("help", "model", "clear", "bye", "drive", "goto", "ros-pub"):
        assert get_command(name) is not None, name


def test_drive_command_invokes_skill() -> None:
    register_builtin_commands()
    cmd = get_command("drive")
    assert cmd is not None
    ctx = DummyCtx()
    asyncio.run(cmd.handler(ctx, "forward 0.5 2"))
    assert ctx.skills_log == [
        ("drive", {"direction": "forward", "speed": 0.5, "duration": 2.0})
    ]


def test_goto_list_routes_to_goto_list_skill() -> None:
    register_builtin_commands()
    cmd = get_command("goto")
    assert cmd is not None
    ctx = DummyCtx()
    asyncio.run(cmd.handler(ctx, "list"))
    assert ctx.skills_log == [("goto_list", {})]


def test_all_commands_unique() -> None:
    register_builtin_commands()
    names = [c.name for c in all_commands()]
    assert len(names) == len(set(names))


def test_common_commands_sorted_before_meta() -> None:
    """常用指令（arm/drive…）應排在系統指令（help/clear/bye）之前，而非字母序。"""
    register_builtin_commands()
    names = [c.name for c in all_commands()]
    assert names[0] == "arm"
    for common in ("arm", "drive", "estop", "goto", "approve"):
        for meta in ("help", "clear", "bye"):
            assert names.index(common) < names.index(meta), (common, meta)
