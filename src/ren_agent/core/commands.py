from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, List, Protocol


class CommandContext(Protocol):
    """提供給指令 handler 使用的介面（由 TUI App 實作）。"""

    async def write_user(self, text: str) -> None:
        ...

    async def write_assistant(self, text: str) -> None:
        ...

    def write_system(self, text: str) -> None:
        ...

    async def ask_llm(self, prompt: str) -> None:
        ...

    def exit_app(self) -> None:
        ...

    async def run_skill(self, name: str, **kwargs) -> None:
        ...


CommandHandler = Callable[[CommandContext, str], Awaitable[None]]


@dataclass
class SlashCommand:
    name: str
    aliases: List[str]
    description: str
    handler: CommandHandler


_COMMANDS: Dict[str, SlashCommand] = {}


def register_command(command: SlashCommand) -> None:
    """註冊單一指令。"""
    for key in [command.name, *command.aliases]:
        _COMMANDS[key] = command


def get_command(name: str) -> SlashCommand | None:
    """依名稱或 alias 取得指令。"""
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


async def _cmd_help(ctx: CommandContext, args: str) -> None:
    ctx.write_system("可用指令：")
    for cmd in all_commands():
        aliases = f" (alias: {', '.join(cmd.aliases)})" if cmd.aliases else ""
        ctx.write_system(f"/{cmd.name}{aliases} — {cmd.description}")


async def _cmd_bye(ctx: CommandContext, args: str) -> None:
    ctx.write_system("結束對話，正在關閉 ren-agent ...")
    ctx.exit_app()


async def _cmd_clear(ctx: CommandContext, args: str) -> None:
    ctx.write_system("已清空對話記錄。")


async def _cmd_model(ctx: CommandContext, args: str) -> None:
    args = args.strip()
    if not args:
        ctx.write_system("使用方式：/model <name>，例如 /model qwen3:8b")
        return
    ctx.write_system(f"切換模型為：{args}")
    await ctx.run_skill("set_model", name=args)


async def _cmd_q(ctx: CommandContext, args: str) -> None:
    query = args.strip()
    if not query:
        ctx.write_system("使用方式：/q <問題內容>")
        return
    await ctx.ask_llm(query)


async def _cmd_ros_topics(ctx: CommandContext, args: str) -> None:
    ctx.write_system("取得 ROS2 topics 中 ...")
    await ctx.run_skill("ros_topics")


async def _cmd_ros_echo(ctx: CommandContext, args: str) -> None:
    topic = args.strip()
    if not topic:
        ctx.write_system("使用方式：/ros echo <topic>")
        return
    ctx.write_system(f"讀取 ROS2 topic: {topic}")
    await ctx.run_skill("ros_echo", topic=topic)


def register_builtin_commands() -> None:
    """供 TUI 啟動時呼叫，註冊所有內建指令。"""
    register_command(
        SlashCommand(
            name="help",
            aliases=[],
            description="顯示可用斜線指令列表",
            handler=_cmd_help,
        )
    )
    register_command(
        SlashCommand(
            name="bye",
            aliases=["exit", "quit"],
            description="關閉 ren-agent",
            handler=_cmd_bye,
        )
    )
    register_command(
        SlashCommand(
            name="clear",
            aliases=[],
            description="清空對話記錄",
            handler=_cmd_clear,
        )
    )
    register_command(
        SlashCommand(
            name="model",
            aliases=[],
            description="切換模型，例如 /model qwen3:8b",
            handler=_cmd_model,
        )
    )
    register_command(
        SlashCommand(
            name="q",
            aliases=["ask"],
            description="快速提問：/q 後面文字會丟給模型",
            handler=_cmd_q,
        )
    )
    register_command(
        SlashCommand(
            name="ros",
            aliases=["ros2"],
            description="ROS2 相關指令（目前支援 topics/echo）",
            handler=_cmd_help,
        )
    )
    register_command(
        SlashCommand(
            name="ros-topics",
            aliases=[],
            description="列出目前 ROS2 topics",
            handler=_cmd_ros_topics,
        )
    )
    register_command(
        SlashCommand(
            name="ros-echo",
            aliases=[],
            description="讀取指定 ROS2 topic 一次",
            handler=_cmd_ros_echo,
        )
    )
