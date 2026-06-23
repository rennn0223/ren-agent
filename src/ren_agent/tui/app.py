"""
ren-agent TUI — Claude Code 風格。

Layout：
  ┌ Chat Log（含開場 welcome panel，會被後續對話捲走）
  ├ Thinking Line（思考中 spinner）
  ├ SlashMenu（/ 指令補全）
  ├ ❯ Input（focus 時橘框）
  └ StatusBar
"""
from __future__ import annotations

import asyncio
from datetime import datetime

from rich.align import Align
from rich.console import Group
from rich.padding import Padding
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.geometry import Size
from textual.reactive import reactive
from textual.strip import Strip
from textual.widgets import Input, RichLog, Static

from ren_agent import __version__
from ren_agent.core.commands import (
    CommandContext,
    all_commands,
    get_command,
    register_builtin_commands,
)
from ren_agent.core.config import DEFAULT_CONFIG_PATH, get_config
from ren_agent.core.ollama_client import OllamaAgent
from ren_agent.core.skills import (
    Skill,
    all_tools,
    register_skill,
    run_skill as core_run_skill,
)
from ren_agent.tools.drive import register_drive_skills
from ren_agent.tools.goto import register_goto_skills
from ren_agent.tools.ros2_skills import register_ros2_skills


# ── Claude Code 配色 ──────────────────────────────────────
C_BG = "#1a1a1a"
C_ORANGE = "#d07d50"
C_CMD = "#a5b4fc"
C_DIM = "#999999"
C_INPUT_BG = "#3a3a3a"
C_INPUT_TEXT = "#ffffff"
C_PLACEHOLDER = "#949494"
C_BORDER = "#606060"

CMD_COL = 22

_BANNER = (
    "██████╗ ███████╗███╗   ██╗      █████╗  ██████╗ ███████╗███╗   ██╗████████╗\n"
    "██╔══██╗██╔════╝████╗  ██║     ██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝\n"
    "██████╔╝█████╗  ██╔██╗ ██║     ███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║\n"
    "██╔══██╗██╔══╝  ██║╚██╗██║     ██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║\n"
    "██║  ██║███████╗██║ ╚████║     ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║\n"
    "╚═╝  ╚═╝╚══════╝╚═╝  ╚═══╝     ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝"
)

_MASCOT = (
    ',                      ," e`--o\n'
    "((                     (  | __,'\n"
    " \\~--------------------\\_;/\n"
    " (                       /\n"
    "  /) ._______________.  )\n"
    " (( (                (( (\n"
    "  ``-'                ``-'"
)

_SPINNER_FRAMES = ("✳", "✦", "✶", "✺")

_HISTORY_FILE = DEFAULT_CONFIG_PATH.parent / "history.txt"
_HISTORY_MAX = 200


# ── Helpers ───────────────────────────────────────────────

def _load_recent_history(n: int = 3) -> list[str]:
    if not _HISTORY_FILE.exists():
        return []
    try:
        lines = [
            ln.strip()
            for ln in _HISTORY_FILE.read_text(encoding="utf-8").splitlines()
            if ln.strip()
        ]
    except Exception:
        return []
    return lines[-n:]


def _append_history(line: str) -> None:
    try:
        _HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        existing = (
            _HISTORY_FILE.read_text(encoding="utf-8").splitlines()
            if _HISTORY_FILE.exists() else []
        )
        existing.append(line)
        existing = existing[-_HISTORY_MAX:]
        _HISTORY_FILE.write_text("\n".join(existing) + "\n", encoding="utf-8")
    except Exception:
        pass


def _build_welcome_panel(model: str) -> Align:
    banner = Align.center(Text(_BANNER, style=f"bold {C_ORANGE}", no_wrap=True))
    mascot = Padding(Text(_MASCOT, style=C_ORANGE, no_wrap=True), (0, 0, 0, 2))
    meta = Padding(Text(f"{model} on Ollama  ·  ~/ren-agent", style=C_DIM), (0, 0, 0, 2))

    left = Group(mascot, Text(""), meta)

    tips_title = Text("Tips for getting started", style=f"bold {C_ORANGE}")
    tips = Text.from_markup(
        f"  [{C_DIM}]Run [/{C_DIM}][{C_CMD}]/help[/{C_CMD}]"
        f"[{C_DIM}] to see all commands[/{C_DIM}]\n"
        f"  [{C_DIM}]Run [/{C_DIM}][{C_CMD}]/ros topics[/{C_CMD}]"
        f"[{C_DIM}] to inspect ROS2 topics[/{C_DIM}]\n"
        f"  [{C_DIM}]Run [/{C_DIM}][{C_CMD}]/drive forward 0.3 1[/{C_CMD}]"
        f"[{C_DIM}] to move the car[/{C_DIM}]\n"
        f"  [{C_DIM}]Run [/{C_DIM}][{C_CMD}]/goto 應科大樓[/{C_CMD}]"
        f"[{C_DIM}] to send a goal[/{C_DIM}]\n"
        f"  [{C_DIM}]Or just ask in natural language — the agent can call tools itself[/{C_DIM}]"
    )

    activity_title = Text("Recent activity", style=f"bold {C_ORANGE}")
    recent = _load_recent_history(3)
    if recent:
        activity = Text("\n".join(f"  {r}" for r in recent), style=C_DIM)
    else:
        activity = Text("  (none)", style=C_DIM)

    right = Group(tips_title, tips, Text(""), activity_title, activity)

    bottom = Table.grid(expand=True, padding=(0, 2))
    bottom.add_column(ratio=1)
    bottom.add_column(ratio=1)
    bottom.add_row(left, right)

    body = Group(banner, Text(""), bottom)

    panel = Panel(
        body,
        title=f"[bold {C_ORANGE}]REN AGENT v{__version__}[/bold {C_ORANGE}]",
        title_align="left",
        border_style=C_ORANGE,
        padding=(1, 2),
        expand=False,
    )
    return Align.center(panel)


# ── Widgets ───────────────────────────────────────────────

class SlashMenu(Static):
    """/ 指令補全清單。"""

    filter_text = reactive("")
    selected_index = reactive(0)

    def _matches(self) -> list[tuple[str, str]]:
        query = self.filter_text.lower().strip()
        if not query.startswith("/"):
            return []
        q = query[1:]
        items: list[tuple[str, str]] = []
        for cmd in all_commands():
            if cmd.name.startswith(q) or any(a.startswith(q) for a in cmd.aliases):
                items.append((f"/{cmd.name}", cmd.description))
        return items

    def selected_cmd(self) -> str | None:
        matches = self._matches()
        if not matches:
            return None
        idx = max(0, min(self.selected_index, len(matches) - 1))
        return matches[idx][0]

    def move_selection(self, delta: int) -> None:
        matches = self._matches()
        if not matches:
            return
        self.selected_index = (self.selected_index + delta) % len(matches)

    def render(self) -> str:
        matches = self._matches()
        if not matches:
            return ""
        idx = max(0, min(self.selected_index, len(matches) - 1))
        lines = []
        for i, (cmd, desc) in enumerate(matches):
            cmd_pad = f"{cmd:<{CMD_COL}}"
            if i == idx:
                lines.append(
                    f"[on #2a2a2a][bold white]{cmd_pad}[/bold white]"
                    f"[{C_DIM}]{desc}[/{C_DIM}][/on #2a2a2a]"
                )
            else:
                lines.append(
                    f"[white]{cmd_pad}[/white]"
                    f"[{C_DIM}]{desc}[/{C_DIM}]"
                )
        return "\n".join(lines)


class CompactRichLog(RichLog):
    """回合制 transcript（user prompt + 助手 streaming）。"""

    CMD_COL = CMD_COL
    _agent_stream_line_count: int = 0

    def write_user(self, message: str) -> None:
        self.write(
            f"[on {C_INPUT_BG} {C_INPUT_TEXT}]› {message}[/on {C_INPUT_BG} {C_INPUT_TEXT}]"
        )

    def write_dim(self, message: str) -> None:
        self.write(f"[{C_DIM}]{message}[/{C_DIM}]")

    def write_error(self, message: str) -> None:
        self.write(f"[red]{message}[/red]")

    def write_system(self, message: str) -> None:
        self.write_dim(message)

    def write_assistant(self, message: str) -> None:
        self.write(message)

    def write_tool_call(self, name: str, args: dict) -> None:
        import json as _json
        args_str = _json.dumps(args, ensure_ascii=False)
        self.write(
            f"[{C_ORANGE}]→[/{C_ORANGE}] [{C_CMD}]{name}[/{C_CMD}]"
            f"[{C_DIM}]({args_str})[/{C_DIM}]"
        )

    def write_tool_result(self, name: str, result: str) -> None:
        first = result.splitlines()[0] if result else ""
        rest = result.splitlines()[1:] if result else []
        self.write(f"[{C_ORANGE}]←[/{C_ORANGE}] [{C_DIM}]{first}[/{C_DIM}]")
        for ln in rest:
            self.write(f"  [{C_DIM}]{ln}[/{C_DIM}]")

    def begin_agent_stream(self) -> None:
        self._agent_stream_line_count = 0
        self.write("")

    def append_agent_stream(self, full_text: str) -> None:
        from rich.segment import Segment

        console = self.app.console
        render_width = max(self.scrollable_content_region.width, self.min_width)
        renderable = Text.from_markup(full_text) if self.markup else Text(full_text)
        render_options = console.options.update_width(render_width)
        if not self.wrap:
            render_options = render_options.update(overflow="ignore", no_wrap=True)

        segments = console.render(renderable, render_options)
        new_strips = [Strip(list(s)) for s in Segment.split_lines(segments)]
        if not new_strips:
            new_strips = [Strip.blank(render_width)]

        old_count = self._agent_stream_line_count or 1
        if len(self.lines) >= old_count:
            del self.lines[-old_count:]

        self.lines.extend(new_strips)
        self._agent_stream_line_count = len(new_strips)

        self._line_cache.clear()
        self.virtual_size = Size(self._widest_line_width, len(self.lines))
        self.scroll_end(animate=False, immediate=False, x_axis=False)
        self.refresh()

    def end_agent_stream(self) -> None:
        self.write("")
        self._agent_stream_line_count = 0


class StatusBar(Static):
    status = reactive("● 初始化中...")

    def render(self) -> str:
        hint_left = "/ for commands · ↑↓ history · tab to complete"
        hint_right = "ctrl+l clear · ctrl+c quit"
        return (
            f"  [{C_DIM}]{self.status}[/{C_DIM}]\n"
            f"  [{C_DIM}]{hint_left}[/{C_DIM}]"
            f"   [{C_DIM}]{hint_right}[/{C_DIM}]"
        )


class ThinkingLine(Static):
    """思考中 spinner。"""

    active = reactive(False)
    _frame = 0

    def on_mount(self) -> None:
        self.set_interval(0.2, self._tick)

    def _tick(self) -> None:
        if self.active:
            self._frame = (self._frame + 1) % len(_SPINNER_FRAMES)
            self.refresh()

    def render(self) -> str:
        if not self.active:
            return ""
        spin = _SPINNER_FRAMES[self._frame]
        return f"[{C_ORANGE}]{spin}[/{C_ORANGE}] [{C_DIM}]思考中...[/{C_DIM}]"


# ── App ───────────────────────────────────────────────────

class RenAgentApp(App):
    TITLE = "REN AGENT"
    CSS = f"""
    Screen {{
        layout: vertical;
        background: {C_BG};
    }}

    #chat-panel {{
        width: 1fr;
        height: 1fr;
        layout: vertical;
        min-height: 3;
    }}

    #chat-log {{
        height: 1fr;
        border: none;
        margin: 0;
        padding: 0 1;
        background: transparent;
        scrollbar-size-vertical: 1;
    }}

    #input-area {{
        height: auto;
        layout: vertical;
    }}

    #slash-menu {{
        height: auto;
        max-height: 8;
        margin: 0 1 0 1;
        padding: 0 1;
        display: none;
    }}

    #slash-menu.-visible {{
        display: block;
    }}

    #thinking-line {{
        height: 1;
        margin: 0 1 0 1;
        display: none;
    }}

    #thinking-line.-visible {{
        display: block;
    }}

    #prompt-zone {{
        height: 3;
        layout: horizontal;
        margin: 0 1;
        border: round {C_BORDER};
        background: {C_INPUT_BG};
        padding: 0 1;
    }}

    #prompt-zone.-focused {{
        border: round {C_ORANGE};
    }}

    #prompt-prefix {{
        width: 3;
        min-width: 3;
        color: {C_PLACEHOLDER};
        background: {C_INPUT_BG};
        content-align: left middle;
        text-style: bold;
    }}

    #prompt-zone.-focused #prompt-prefix {{
        color: {C_ORANGE};
    }}

    #user-input {{
        width: 1fr;
        height: 1;
        border: none;
        background: {C_INPUT_BG};
        color: {C_INPUT_TEXT};
        padding: 0;
    }}

    #user-input:focus {{
        border: none;
        background: {C_INPUT_BG};
    }}

    #user-input > .input--placeholder {{
        color: {C_PLACEHOLDER};
    }}

    #status-bar {{
        height: auto;
        background: transparent;
        padding: 0 1 1 1;
        color: {C_DIM};
    }}
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "離開", priority=True),
        Binding("ctrl+l", "clear_chat", "清空對話", show=True),
        Binding("ctrl+n", "new_session", "新對話", show=True),
        Binding("tab", "slash_complete", "Slash 補全", show=False, priority=True),
        Binding("up", "slash_up", "上一個 / history", show=False, priority=True),
        Binding("down", "slash_down", "下一個 / history", show=False, priority=True),
    ]

    def __init__(
        self,
        model: str = "qwen3.6:35b",
        ollama_host: str = "http://localhost:11434",
    ):
        super().__init__()
        self.config = get_config()
        self.config.ollama.model = model
        self.config.ollama.host = ollama_host
        self.agent = OllamaAgent(config=self.config.ollama)
        self.agent.set_system_prompt(self.config.agent.system_prompt)

        self._thinking = False
        self._pending_queue: list[tuple[str, str]] = []

        self._input_history: list[str] = _load_recent_history(_HISTORY_MAX)
        self._input_history_index: int | None = None
        self._last_response_at: str | None = None

    # ── Widget helpers ───────────────────────────────────

    def _chat(self) -> CompactRichLog:
        return self.query_one("#chat-log", CompactRichLog)

    def _input(self) -> Input:
        return self.query_one("#user-input", Input)

    # ── Compose ──────────────────────────────────────────

    def compose(self) -> ComposeResult:
        with Vertical(id="chat-panel"):
            yield CompactRichLog(
                id="chat-log", highlight=True, markup=True, wrap=True,
            )

        with Vertical(id="input-area"):
            yield ThinkingLine(id="thinking-line")
            yield SlashMenu(id="slash-menu")
            with Horizontal(id="prompt-zone"):
                yield Static(">", id="prompt-prefix")
                yield Input(
                    placeholder="Ask a question...",
                    id="user-input",
                    compact=True,
                )

        yield StatusBar(id="status-bar")

    def on_mount(self) -> None:
        # 註冊指令與 skills（先註冊，welcome panel 才能反映 /help）
        register_builtin_commands()
        register_ros2_skills()
        register_drive_skills()
        register_goto_skills()
        register_skill(
            Skill("set_model", "切換 Ollama 模型", self._set_model_skill)
        )

        # 開場 welcome panel：寫進 chat-log 當第一筆，後續對話會自然往下捲
        chat = self._chat()
        chat.write(_build_welcome_panel(self.config.ollama.model))
        chat.write("")

        self.check_ollama()
        self._input().focus()
        self._refresh_focus_style()

    # ── Skill ────────────────────────────────────────────

    async def _set_model_skill(self, name: str) -> str:
        name = name.strip()
        old = self.config.ollama.model
        if not name:
            return f"目前模型：{old}"
        self.config.ollama.model = name
        self.agent = OllamaAgent(config=self.config.ollama)
        self.agent.set_system_prompt(self.config.agent.system_prompt)
        self.query_one(StatusBar).status = f"● 已切換模型為 {name}"
        return f"模型已從 {old} 切換為 {name}"

    # ── 佇列 ─────────────────────────────────────────────

    def _slash_cmd(self, raw: str) -> str:
        parts = raw[1:].strip().split()
        return parts[0].lower() if parts else ""

    def _format_queue_label(self) -> str:
        if not self._pending_queue:
            return ""
        labels = []
        for kind, content in self._pending_queue:
            if kind == "slash":
                labels.append(content)
            else:
                preview = content if len(content) <= 24 else content[:21] + "..."
                labels.append(f'"{preview}"')
        return f"（{', '.join(labels)}）"

    def _update_queue_status(self) -> None:
        status = self.query_one(StatusBar)
        pending = len(self._pending_queue)
        base = f"{self.config.ollama.model}"
        if self._last_response_at:
            base = f"{base} · last {self._last_response_at}"
        if pending:
            status.status = (
                f"⟳ 思考中 · 佇列 {pending} 則"
                f"{self._format_queue_label()} · {base}"
            )
        else:
            status.status = f"● 就緒 · {base}"

    def _enqueue(self, kind: str, content: str) -> None:
        if self._thinking:
            self._pending_queue.append((kind, content))
            self._update_queue_status()
            return
        if kind == "message":
            self.stream_response(content)
        else:
            self.execute_slash_command(content)

    def _enqueue_message(self, content: str) -> None:
        self._enqueue("message", content)

    def _enqueue_slash(self, raw: str) -> None:
        self._enqueue("slash", raw)

    def _drain_queue(self) -> None:
        if not self._pending_queue:
            self._update_queue_status()
            return
        kind, content = self._pending_queue.pop(0)
        if self._pending_queue:
            self._update_queue_status()
        if kind == "message":
            self.stream_response(content)
        else:
            self.execute_slash_command(content)

    def _work_finished(self) -> None:
        self._thinking = False
        self._set_thinking(False)
        self.refresh(layout=True)
        self._drain_queue()

    # ── SlashMenu ────────────────────────────────────────

    def _update_slash_menu(self, value: str) -> None:
        menu = self.query_one("#slash-menu", SlashMenu)
        if value.startswith("/"):
            menu.filter_text = value
            menu.selected_index = 0
            menu.add_class("-visible")
        else:
            menu.filter_text = ""
            menu.remove_class("-visible")

    def action_slash_up(self) -> None:
        menu = self.query_one("#slash-menu", SlashMenu)
        if "-visible" in menu.classes:
            menu.move_selection(-1)
            return
        self._history_prev()

    def action_slash_down(self) -> None:
        menu = self.query_one("#slash-menu", SlashMenu)
        if "-visible" in menu.classes:
            menu.move_selection(1)
            return
        self._history_next()

    def action_slash_complete(self) -> None:
        input_widget = self._input()
        menu = self.query_one("#slash-menu", SlashMenu)
        if not input_widget.value.startswith("/"):
            return
        completion = menu.selected_cmd()
        if not completion:
            return
        new_text = completion + " "
        input_widget.value = new_text
        input_widget.cursor_position = len(new_text)
        menu.filter_text = ""
        menu.remove_class("-visible")

    # ── Input history ────────────────────────────────────

    def _history_prev(self) -> None:
        if not self._input_history:
            return
        input_widget = self._input()
        if self._input_history_index is None:
            self._input_history_index = len(self._input_history) - 1
        elif self._input_history_index > 0:
            self._input_history_index -= 1
        input_widget.value = self._input_history[self._input_history_index]
        input_widget.cursor_position = len(input_widget.value)

    def _history_next(self) -> None:
        if self._input_history_index is None:
            return
        input_widget = self._input()
        if self._input_history_index < len(self._input_history) - 1:
            self._input_history_index += 1
            input_widget.value = self._input_history[self._input_history_index]
        else:
            self._input_history_index = None
            input_widget.value = ""
        input_widget.cursor_position = len(input_widget.value)

    # ── Input 事件 ───────────────────────────────────────

    async def on_input_changed(self, event: Input.Changed) -> None:
        self._update_slash_menu(event.value)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        message = event.value.strip()
        if not message:
            return

        menu = self.query_one("#slash-menu", SlashMenu)
        if "-visible" in menu.classes:
            self.action_slash_complete()
            return

        event.input.clear()
        self._update_slash_menu("")

        self._input_history.append(message)
        self._input_history_index = None
        _append_history(message)

        if message.startswith("/"):
            if self._slash_cmd(message) in ("bye", "exit", "quit"):
                await self.handle_slash_command(message)
                return
            if self._thinking:
                self._enqueue_slash(message)
                return
            handled = await self.handle_slash_command(message)
            if handled:
                return
            self._enqueue_message(message)
            return

        self._enqueue_message(message)

    # ── Focus / 樣式 ─────────────────────────────────────

    def _refresh_focus_style(self) -> None:
        zone = self.query_one("#prompt-zone")
        if self._input().has_focus:
            zone.add_class("-focused")
        else:
            zone.remove_class("-focused")

    def on_descendant_focus(self) -> None:
        self._refresh_focus_style()

    def on_descendant_blur(self) -> None:
        self._refresh_focus_style()

    def _set_thinking(self, active: bool) -> None:
        line = self.query_one("#thinking-line", ThinkingLine)
        line.active = active
        if active:
            line.add_class("-visible")
        else:
            line.remove_class("-visible")

    # ── Ollama 連線檢查 ──────────────────────────────────

    @work(thread=True)
    def check_ollama(self) -> None:
        status = self.query_one(StatusBar)
        ok = asyncio.run(self.agent.check_connection())
        if ok:
            msg = f"● 已連線 Ollama ({self.config.ollama.model})"
        else:
            msg = "✗ Ollama 未啟動 — 請執行: ollama serve"
        self.call_from_thread(setattr, status, "status", msg)

    # ── Streaming ────────────────────────────────────────

    @work(exclusive=True)
    async def stream_response(self, message: str) -> None:
        self._thinking = True
        chat = self._chat()
        status = self.query_one(StatusBar)
        self._set_thinking(True)
        status.status = f"⟳ 思考中... · {self.config.ollama.model}"

        chat.write_user(message)
        block_text = ""
        chat.begin_agent_stream()

        async def _on_tool(name: str, args: dict, result: str) -> None:
            nonlocal block_text
            chat.end_agent_stream()
            chat.write_tool_call(name, args)
            chat.write_tool_result(name, result)
            block_text = ""
            chat.begin_agent_stream()

        try:
            async for token in self.agent.chat_stream(
                message,
                tools=all_tools() or None,
                on_tool_call=_on_tool,
            ):
                block_text += token
                chat.append_agent_stream(block_text)
            chat.end_agent_stream()
        except Exception as e:  # noqa: BLE001
            chat.write_error(f"串流錯誤：{e}")
        finally:
            self._last_response_at = datetime.now().strftime("%H:%M:%S")
            self._work_finished()

    @work(exclusive=True)
    async def execute_slash_command(self, raw: str) -> None:
        self._thinking = True
        self._set_thinking(True)
        self.query_one(StatusBar).status = (
            f"⟳ 執行 {raw} · {self.config.ollama.model}"
        )
        try:
            await self.handle_slash_command(raw)
        finally:
            self._work_finished()

    # ── Slash command 派發 ───────────────────────────────

    async def handle_slash_command(self, raw: str) -> bool:
        chat = self._chat()
        text = raw.lstrip("/")
        if not text:
            chat.write_system("空的指令。")
            return True

        parts = text.split(maxsplit=2)
        cmd = parts[0].lower()
        sub = parts[1] if len(parts) > 1 else ""
        rest = parts[2] if len(parts) > 2 else ""

        # /ros <sub> ...  →  ros-<sub>
        if cmd in ("ros", "ros2"):
            if sub in ("topics", "echo", "type", "pub"):
                cmd_key = f"ros-{sub}"
                args = rest
            else:
                chat.write_system("用法：/ros topics|echo|type|pub <topic> [...]")
                return True
        else:
            cmd_key = cmd
            args = (sub + (" " + rest if rest else "")).strip()

        command = get_command(cmd_key)
        if not command:
            chat.write_dim(f"未知指令：/{cmd_key}，視為一般訊息送給 Agent。")
            return False

        ctx = self._CommandCtx(self)
        chat.write_user(raw)

        if cmd_key == "clear":
            chat.clear()
            self.agent.reset_history()
            self._pending_queue.clear()
            self._update_queue_status()

        await command.handler(ctx, args)
        return True

    # ── Action handlers ──────────────────────────────────

    def action_clear_chat(self) -> None:
        self._chat().clear()
        self.agent.reset_history()
        self._pending_queue.clear()
        self._update_queue_status()

    def action_new_session(self) -> None:
        self.action_clear_chat()

    # ── CommandContext ───────────────────────────────────

    class _CommandCtx(CommandContext):
        def __init__(self, app: "RenAgentApp") -> None:
            self.app = app

        async def write_user(self, text: str) -> None:
            self.app._chat().write_user(text)

        async def write_assistant(self, text: str) -> None:
            self.app._chat().write_assistant(text)

        def write_system(self, text: str) -> None:
            self.app._chat().write_system(text)

        def write_renderable(self, obj) -> None:
            self.app._chat().write(obj)

        async def ask_llm(self, prompt: str) -> None:
            self.app._enqueue_message(prompt)

        def exit_app(self) -> None:
            self.app.exit()

        async def run_skill(self, skill: str, **kwargs) -> None:
            try:
                result = await core_run_skill(skill, **kwargs)
            except Exception as e:  # noqa: BLE001
                result = f"skill `{skill}` 失敗：{e}"
            self.app._chat().write_system(result)
