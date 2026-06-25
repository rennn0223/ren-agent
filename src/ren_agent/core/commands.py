"""
Slash command registry。

每個指令是一個 SlashCommand（name + aliases + description + handler）。
TUI 收到 `/xxx` 後：
  1. parse 出 cmd / args
  2. get_command(cmd) 找到對應 SlashCommand
  3. 呼叫 handler(ctx, args)

handler 不直接動 TUI widget，而是透過 CommandContext 寫文字 / 呼 skill /
退出。這樣 handler 可以被測試（mock 一個 DummyCtx 即可）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Protocol


# ── CommandContext Protocol ─────────────────────────────────
# handler 透過這個介面跟 TUI 對話；實作在 tui/app.py 的 _CommandCtx
class CommandContext(Protocol):
    """提供給指令 handler 使用的介面（由 TUI App 實作）。"""

    async def write_user(self, text: str) -> None: ...
    async def write_assistant(self, text: str) -> None: ...
    def write_system(self, text: str) -> None: ...
    def write_renderable(self, obj: Any) -> None: ...    # 寫任意 Rich 物件
    async def ask_llm(self, prompt: str) -> None: ...     # 進入 LLM 對話流程
    def exit_app(self) -> None: ...
    async def run_skill(self, skill: str, **kwargs) -> None: ...


CommandHandler = Callable[[CommandContext, str], Awaitable[None]]


@dataclass
class SlashCommand:
    name: str                    # 主名稱（不含 /）
    aliases: List[str]           # 別名清單，如 bye 的 exit, quit
    description: str             # 顯示在 /help 與 SlashMenu
    handler: CommandHandler      # 實際執行函式


# ── Registry ─────────────────────────────────────────
# 用同一個 dict 同時儲存 name 與 alias → SlashCommand
_COMMANDS: Dict[str, SlashCommand] = {}


def register_command(command: SlashCommand) -> None:
    """主名稱與所有 alias 都會指向同一個 SlashCommand 物件。"""
    for key in [command.name, *command.aliases]:
        _COMMANDS[key] = command


def get_command(name: str) -> SlashCommand | None:
    """名稱或 alias 都可查。"""
    return _COMMANDS.get(name)


def all_commands() -> List[SlashCommand]:
    """
    去重後依名稱排序（給 SlashMenu / /help 用）。
    因為 alias 與主名稱都在 _COMMANDS 裡，要過濾掉重複的物件。
    """
    seen: set[str] = set()
    results: List[SlashCommand] = []
    for cmd in _COMMANDS.values():
        if cmd.name in seen:
            continue
        seen.add(cmd.name)
        results.append(cmd)
    return sorted(results, key=lambda c: c.name)


# ── Handlers ─────────────────────────────────────────
# 每個 handler 簽名都是 (ctx, args_str)，args_str 是 / 後面的整段文字

async def _cmd_help(ctx: CommandContext, args: str) -> None:
    """/help — 用 Rich Table 顯示所有指令（指令｜描述｜alias）。"""
    from rich.console import Group
    from rich.table import Table
    from rich.text import Text

    table = Table.grid(padding=(0, 2))
    table.add_column(style="#a5b4fc", no_wrap=True)   # 指令名（淺紫）
    table.add_column(style="#999999")                  # 描述（灰）
    table.add_column(style="#666666", no_wrap=True)    # alias（深灰）

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
    """/bye, /exit, /quit — 關閉 TUI。"""
    ctx.write_system("結束對話，正在關閉 ren-agent ...")
    ctx.exit_app()


async def _cmd_clear(ctx: CommandContext, args: str) -> None:
    """/clear — 實際清空在 TUI 端做（chat.clear + agent.reset_history），這裡只回一句訊息。"""
    ctx.write_system("已清空對話記錄。")


async def _cmd_model(ctx: CommandContext, args: str) -> None:
    """/model <name> — 透過 set_model skill 切換模型。"""
    args = args.strip()
    if not args:
        ctx.write_system("用法：/model <name>，例如 /model qwen3:8b")
        return
    await ctx.run_skill("set_model", name=args)


# ── ROS2 相關 ──
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
    """/ros pub <topic> <json_payload> — 自動推斷型別、填欄位、發布。"""
    parts = args.split(maxsplit=1)
    if len(parts) < 2:
        ctx.write_system('用法：/ros pub <topic> <json>，例如 /ros pub /chatter {"data":"hi"}')
        return
    topic, payload = parts
    await ctx.run_skill("ros_publish", topic=topic, payload=payload)


async def _cmd_domain(ctx: CommandContext, args: str) -> None:
    """/domain <id> [rmw] — 動態切換 ROS_DOMAIN_ID（會重啟 ROS2 節點）。"""
    parts = args.split()
    if not parts:
        ctx.write_system("用法：/domain <id> [rmw]，例如 /domain 30 rmw_fastrtps_cpp")
        return
    domain_id = parts[0]
    rmw = parts[1] if len(parts) > 1 else None
    await ctx.run_skill("set_domain", domain_id=domain_id, rmw=rmw)


async def _cmd_agent(ctx: CommandContext, args: str) -> None:
    """/agent [cmd] — 發指令給 AI agent 控制端，預設 go_agent_route。"""
    cmd = args.strip() or "go_agent_route"
    await ctx.run_skill("agent_command", cmd=cmd)


async def _cmd_estop(ctx: CommandContext, args: str) -> None:
    """/estop — 緊急停止車輛（立即送 0 速度）。"""
    await ctx.run_skill("estop")


async def _cmd_route(ctx: CommandContext, args: str) -> None:
    """/route <起點> <終點> — 規劃路線、發布 go_agent_route 並印出座標。"""
    parts = args.split()
    if len(parts) < 2:
        ctx.write_system("用法：/route <起點> <終點>，例如 /route 應科 機械系館")
        return
    await ctx.run_skill("route", start=parts[0], goal=parts[1])


# ── 車輛控制 ──
async def _cmd_drive(ctx: CommandContext, args: str) -> None:
    """/drive forward|back|left|right|stop [speed] [duration]."""
    parts = args.split()
    if not parts:
        ctx.write_system("用法：/drive forward|back|left|right|stop [speed] [duration_sec]")
        return
    direction = parts[0].lower()
    # 沒給就用預設：0.3 m/s, 1 秒
    speed = float(parts[1]) if len(parts) > 1 else 0.3
    duration = float(parts[2]) if len(parts) > 2 else 1.0
    await ctx.run_skill("drive", direction=direction, speed=speed, duration=duration)


async def _cmd_goto(ctx: CommandContext, args: str) -> None:
    """/goto <地名> 或 /goto list."""
    name = args.strip()
    if not name:
        ctx.write_system("用法：/goto <地名>，可先用 /goto list 看清單")
        return
    if name == "list":
        await ctx.run_skill("goto_list")
        return
    await ctx.run_skill("goto", name=name)


# ── 註冊入口 ────────────────────────────────────────
def register_builtin_commands() -> None:
    """TUI on_mount() 啟動時呼叫一次，把所有內建指令塞進 registry。"""
    register_command(SlashCommand("help", [], "顯示可用斜線指令列表", _cmd_help))
    register_command(SlashCommand("bye", ["exit", "quit"], "關閉 ren-agent", _cmd_bye))
    register_command(SlashCommand("clear", [], "清空對話記錄", _cmd_clear))
    register_command(SlashCommand("model", [], "切換模型，例如 /model qwen3:8b", _cmd_model))
    register_command(SlashCommand("ros-topics", [], "列出目前 ROS2 topics", _cmd_ros_topics))
    register_command(SlashCommand("ros-echo", [], "讀取指定 ROS2 topic 一次", _cmd_ros_echo))
    register_command(SlashCommand("ros-type", [], "查詢指定 topic 的訊息型別", _cmd_ros_type))
    register_command(SlashCommand("ros-pub", [], "發布 JSON 到 topic（自動推斷型別）", _cmd_ros_pub))
    register_command(SlashCommand("drive", [], "控制車子：forward/back/left/right/stop", _cmd_drive))
    register_command(SlashCommand("estop", ["stop"], "緊急停止車輛（立即送 0 速度）", _cmd_estop))
    register_command(SlashCommand("goto", [], "送出地點座標給 Isaac Sim", _cmd_goto))
    register_command(SlashCommand("domain", [], "切換 ROS_DOMAIN_ID，例如 /domain 30", _cmd_domain))
    register_command(SlashCommand("agent", [], "發指令給 AI agent，例如 /agent go_agent_route", _cmd_agent))
    register_command(
        SlashCommand("route", [], "規劃路線：/route <起點> <終點>", _cmd_route)
    )
