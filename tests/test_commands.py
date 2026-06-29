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
    for name in ("help", "model", "clear", "bye", "drive", "goto", "ros-pub", "setspeed"):
        assert get_command(name) is not None, name


def test_drive_second_unit() -> None:
    """forward 3 second → duration=3, speed=預設線速度 1.0"""
    register_builtin_commands()
    cmd = get_command("drive")
    assert cmd is not None
    ctx = DummyCtx()
    asyncio.run(cmd.handler(ctx, "forward 3 second"))
    assert ctx.skills_log == [("drive", {"direction": "forward", "speed": 1.0, "duration": 3.0})]


def test_drive_meter_unit() -> None:
    """forward 2 meter → effective_speed = min(1.0, max_linear_speed=0.5) = 0.5 → duration = 4.0"""
    register_builtin_commands()
    cmd = get_command("drive")
    assert cmd is not None
    ctx = DummyCtx()
    asyncio.run(cmd.handler(ctx, "forward 2 meter"))
    assert ctx.skills_log == [("drive", {"direction": "forward", "speed": 0.5, "duration": 4.0})]


def test_drive_meter_unit_aliases() -> None:
    """meters / m 都合法；effective_speed = min(1.0, 0.5) = 0.5 → back 1 meter = 2.0s"""
    register_builtin_commands()
    cmd = get_command("drive")
    assert cmd is not None
    for unit in ("meters", "m"):
        ctx = DummyCtx()
        asyncio.run(cmd.handler(ctx, f"back 1 {unit}"))
        assert ctx.skills_log == [("drive", {"direction": "back", "speed": 0.5, "duration": 2.0})], unit


def test_drive_second_aliases() -> None:
    """seconds / sec / s 都合法"""
    register_builtin_commands()
    cmd = get_command("drive")
    assert cmd is not None
    for unit in ("seconds", "sec", "s"):
        ctx = DummyCtx()
        asyncio.run(cmd.handler(ctx, f"forward 2 {unit}"))
        assert ctx.skills_log == [("drive", {"direction": "forward", "speed": 1.0, "duration": 2.0})], unit


def test_drive_stop_no_unit() -> None:
    """/drive stop 不需要單位"""
    register_builtin_commands()
    cmd = get_command("drive")
    assert cmd is not None
    ctx = DummyCtx()
    asyncio.run(cmd.handler(ctx, "stop"))
    assert ctx.skills_log == [("drive", {"direction": "stop", "speed": 0.0, "duration": 0.0})]


def test_drive_angular_uses_angular_speed() -> None:
    """left/right 用 angular 預設速度 0.3"""
    register_builtin_commands()
    cmd = get_command("drive")
    assert cmd is not None
    ctx = DummyCtx()
    asyncio.run(cmd.handler(ctx, "left 3 second"))
    assert ctx.skills_log == [("drive", {"direction": "left", "speed": 0.3, "duration": 3.0})]


def test_drive_angular_meter_rejected() -> None:
    """left/right + meter 應被拒絕，角度方向無法用 meter 換算 duration"""
    register_builtin_commands()
    cmd = get_command("drive")
    assert cmd is not None
    for direction in ("left", "right"):
        ctx = DummyCtx()
        asyncio.run(cmd.handler(ctx, f"{direction} 1 meter"))
        assert ctx.skills_log == [], direction
        assert any("meter" in m and "forward" in m for m in ctx.system), direction


def test_drive_invalid_unit_shows_error() -> None:
    register_builtin_commands()
    cmd = get_command("drive")
    assert cmd is not None
    ctx = DummyCtx()
    asyncio.run(cmd.handler(ctx, "forward 2 km/h"))
    assert ctx.skills_log == []
    assert any("不支援的單位" in m for m in ctx.system)


def test_drive_missing_unit_shows_usage() -> None:
    register_builtin_commands()
    cmd = get_command("drive")
    assert cmd is not None
    ctx = DummyCtx()
    asyncio.run(cmd.handler(ctx, "forward 2"))
    assert ctx.skills_log == []
    assert any("用法" in m for m in ctx.system)


def test_drive_invalid_direction_shows_error() -> None:
    register_builtin_commands()
    cmd = get_command("drive")
    assert cmd is not None
    ctx = DummyCtx()
    asyncio.run(cmd.handler(ctx, "sideways 2 meter"))
    assert ctx.skills_log == []
    assert any("未知方向" in m for m in ctx.system)


def test_setspeed_updates_drive_speed() -> None:
    """setspeed 設低於 safety 上限的值後，drive meter 用新速度計算 duration"""
    import ren_agent.core.commands as _cmds
    register_builtin_commands()
    # reset to known state
    _cmds._drive_linear_speed = 1.0
    _cmds._drive_angular_speed = 0.3

    setspeed_cmd = get_command("setspeed")
    assert setspeed_cmd is not None
    ctx = DummyCtx()
    # 0.4 < max_linear_speed(0.5)，effective_speed = 0.4
    asyncio.run(setspeed_cmd.handler(ctx, "0.4 0.2"))
    assert _cmds._drive_linear_speed == 0.4
    assert _cmds._drive_angular_speed == 0.2

    # forward 2 meter: effective = min(0.4, 0.5) = 0.4 → duration = 5.0
    drive_cmd = get_command("drive")
    ctx2 = DummyCtx()
    asyncio.run(drive_cmd.handler(ctx2, "forward 2 meter"))
    assert ctx2.skills_log == [("drive", {"direction": "forward", "speed": 0.4, "duration": 5.0})]

    # restore
    _cmds._drive_linear_speed = 1.0
    _cmds._drive_angular_speed = 0.3


def test_setspeed_no_args_shows_current() -> None:
    register_builtin_commands()
    cmd = get_command("setspeed")
    assert cmd is not None
    ctx = DummyCtx()
    asyncio.run(cmd.handler(ctx, ""))
    assert any("目前速度" in m for m in ctx.system)


def test_setspeed_invalid_shows_error() -> None:
    register_builtin_commands()
    cmd = get_command("setspeed")
    assert cmd is not None
    ctx = DummyCtx()
    asyncio.run(cmd.handler(ctx, "-1 0.3"))
    assert any("必須 > 0" in m for m in ctx.system)


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
