from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Protocol


class CommandContext(Protocol):
    """提供給指令 handler 使用的介面（由 TUI App 實作）。"""

    async def write_user(self, text: str) -> None: ...
    async def write_assistant(self, text: str) -> None: ...
    def write_system(self, text: str) -> None: ...
    def write_renderable(self, obj: Any) -> None: ...
    async def ask_llm(self, prompt: str) -> None: ...
    def exit_app(self) -> None: ...
    async def run_skill(self, skill: str, **kwargs) -> None: ...


CommandHandler = Callable[[CommandContext, str], Awaitable[None]]


@dataclass
class SlashCommand:
    name: str
    aliases: List[str]
    description: str
    handler: CommandHandler


_COMMANDS: Dict[str, SlashCommand] = {}


def register_command(command: SlashCommand) -> None:
    for key in [command.name, *command.aliases]:
        _COMMANDS[key] = command


def get_command(name: str) -> SlashCommand | None:
    return _COMMANDS.get(name)


def all_commands() -> List[SlashCommand]:
    """列出所有指令（給 SlashMenu 用）。"""
    seen: set[str] = set()
    results: List[SlashCommand] = []
    for cmd in _COMMANDS.values():
        if cmd.name in seen:
            continue
        seen.add(cmd.name)
        results.append(cmd)
    return sorted(results, key=lambda c: c.name)


# ── Handlers ────────────────────────────────────────────────

async def _cmd_help(ctx: CommandContext, args: str) -> None:
    from rich.console import Group
    from rich.table import Table
    from rich.text import Text

    table = Table.grid(padding=(0, 2))
    table.add_column(style="#a5b4fc", no_wrap=True)   # command
    table.add_column(style="#999999")                  # description
    table.add_column(style="#666666", no_wrap=True)    # alias

    for cmd in all_commands():
        alias = f"alias: {', '.join(cmd.aliases)}" if cmd.aliases else ""
        table.add_row(f"/{cmd.name}", cmd.description, alias)

    header = Text("Available commands", style="bold #d07d50")
    footer = Text(
        "  enter send · tab complete · ↑↓ history · ctrl+l clear",
        style="#666666",
    )
    ctx.write_renderable(Group(Text(""), header, table, Text(""), footer))


async def _cmd_bye(ctx: CommandContext, args: str) -> None:
    ctx.write_system("結束對話，正在關閉 ren-agent ...")
    ctx.exit_app()


async def _cmd_clear(ctx: CommandContext, args: str) -> None:
    ctx.write_system("已清空對話記錄。")


async def _cmd_model(ctx: CommandContext, args: str) -> None:
    args = args.strip()
    if not args:
        ctx.write_system("用法：/model <name>，例如 /model qwen3:8b")
        return
    await ctx.run_skill("set_model", name=args)


async def _cmd_ros_topics(ctx: CommandContext, args: str) -> None:
    await ctx.run_skill("ros_topics")


async def _cmd_ros_echo(ctx: CommandContext, args: str) -> None:
    topic = args.strip()
    if not topic:
        ctx.write_system("用法：/ros echo <topic>")
        return
    await ctx.run_skill("ros_echo", topic=topic)


async def _cmd_ros_type(ctx: CommandContext, args: str) -> None:
    topic = args.strip()
    if not topic:
        ctx.write_system("用法：/ros type <topic>")
        return
    await ctx.run_skill("ros_type", topic=topic)


async def _cmd_ros_pub(ctx: CommandContext, args: str) -> None:
    """/ros pub <topic> <json_payload>"""
    parts = args.split(maxsplit=1)
    if len(parts) < 2:
        ctx.write_system('用法：/ros pub <topic> <json>，例如 /ros pub /chatter {"data":"hi"}')
        return
    topic, payload = parts
    await ctx.run_skill("ros_publish", topic=topic, payload=payload)


async def _cmd_drive(ctx: CommandContext, args: str) -> None:
    """/drive forward|back|left|right|stop [speed] [duration]"""
    parts = args.split()
    if not parts:
        ctx.write_system("用法：/drive forward|back|left|right|stop [speed] [duration_sec]")
        return
    direction = parts[0].lower()
    speed = float(parts[1]) if len(parts) > 1 else 0.3
    duration = float(parts[2]) if len(parts) > 2 else 1.0
    await ctx.run_skill("drive", direction=direction, speed=speed, duration=duration)


async def _cmd_goto(ctx: CommandContext, args: str) -> None:
    """/goto <地名> 或 /goto list"""
    name = args.strip()
    if not name:
        ctx.write_system("用法：/goto <地名>，可先用 /goto list 看清單")
        return
    if name == "list":
        await ctx.run_skill("goto_list")
        return
    await ctx.run_skill("goto", name=name)


def register_builtin_commands() -> None:
    register_command(SlashCommand("help", [], "顯示可用斜線指令列表", _cmd_help))
    register_command(SlashCommand("bye", ["exit", "quit"], "關閉 ren-agent", _cmd_bye))
    register_command(SlashCommand("clear", [], "清空對話記錄", _cmd_clear))
    register_command(SlashCommand("model", [], "切換模型，例如 /model qwen3:8b", _cmd_model))
    register_command(SlashCommand("ros-topics", [], "列出目前 ROS2 topics", _cmd_ros_topics))
    register_command(SlashCommand("ros-echo", [], "讀取指定 ROS2 topic 一次", _cmd_ros_echo))
    register_command(SlashCommand("ros-type", [], "查詢指定 topic 的訊息型別", _cmd_ros_type))
    register_command(
        SlashCommand("ros-pub", [], "發布 JSON 到 topic（自動推斷型別）", _cmd_ros_pub)
    )
    register_command(
        SlashCommand("drive", [], "控制車子：forward/back/left/right/stop", _cmd_drive)
    )
    register_command(SlashCommand("goto", [], "送出地點座標給 Isaac Sim", _cmd_goto))
