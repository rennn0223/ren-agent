"""
ren-agent TUI 主介面 — v0.3.0


風格參考 Claude Code：
  - 橘色框 welcome card，標題 REN AGENT v0.2.0 嵌入上邊框（永遠顯示）
  - 左欄：Welcome / 臘腸狗 / 模型資訊垂直置中；右欄 Tips + Recent activity
  - Streaming token 即時顯示
  - SlashMenu 上下鍵選取 + Tab/Enter 補全
  - ROS2 真實 subprocess 整合（改為 Skills 介面）
  - 回合制對話：忙碌時可排隊，輪到才顯示使用者訊息並串流回覆（Claude/Codex 邏輯）
  - Slash Command Registry + Skill 介面（v0.3.0）
"""
from __future__ import annotations

import asyncio
from datetime import datetime

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical
from textual.geometry import Size
from textual.reactive import reactive
from textual.strip import Strip
from textual.widgets import Input, RichLog, Rule, Static

from ren_agent.core.config import get_config
from ren_agent.core.ollama_client import OllamaAgent
from ren_agent.core.commands import (
    CommandContext,
    get_command,
    register_builtin_commands,
)
from ren_agent.core.skills import Skill, run_skill as core_run_skill, register_skill
from ren_agent.tools.ros2_skills import register_ros2_skills


# Claude Code 配色
C_BG = "#1a1a1a"
C_ORANGE = "#d07d50"
C_CMD = "#a5b4fc"
C_DIM = "#999999"
C_RULE = "#808080"
C_INPUT_BG = "#3a3a3a"
C_INPUT_TEXT = "#ffffff"
C_PLACEHOLDER = "#949494"
C_BORDER = "#606060"


# 臘腸狗最寬一行 37 字元、共 7 行
MASCOT_WIDTH = 38
MASCOT_HEIGHT = 7

HERO_VERSION = "v0.3.0"

_MASCOT_LINES = (
    ',                      ," e`--o',
    "((                     (  | __,'",
    " \\~--------------------\\_;/",
    " (                       /",
    "  /) ._______________.  )",
    " (( (                (( (",
    "  ``-'                ``-'",
)

# 斜線指令欄位對齊寬度
CMD_COL = 22


class MascotArt(Static):
    """臘腸狗 ASCII，固定行數避免被裁切。"""

    def render(self) -> str:
        body = "\n".join(_MASCOT_LINES)
        return f"[bold {C_ORANGE}]{body}[/bold {C_ORANGE}]"


class HeroCard(Vertical):
    """Claude Code 風格 welcome 卡片，標題嵌入上邊框。"""

    BORDER_TITLE = f"REN AGENT {HERO_VERSION}"


# 仍維持給 SlashMenu 用的指令清單（行為由 registry 控制）
SLASH_COMMANDS: list[tuple[str, str]] = [
    ("/q", "快速提問，後面文字會丟給模型"),
    ("/help", "顯示可用斜線指令"),
    ("/clear", "清空對話記錄"),
    ("/bye", "結束並關閉 ren-agent"),
    ("/model", "切換模型，例如 /model qwen3:8b"),
    ("/ros topics", "列出目前 ROS2 topics"),
    ("/ros echo", "讀取指定 topic，例如 /ros echo /odom"),
]


class SlashMenu(Static):
    """
    輸入 / 時顯示指令補全清單。
    支援上下鍵選取（selected_index）、Tab/Enter 補全。
    """

    filter_text = reactive("")
    selected_index = reactive(0)

    def _matches(self) -> list[tuple[str, str]]:
        query = self.filter_text.lower().strip()
        if not query.startswith("/"):
            return []
        return [
            (cmd, desc)
            for cmd, desc in SLASH_COMMANDS
            if cmd.startswith(query)
        ]

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
            if i == idx:
                line = (
                    f"[bold {C_ORANGE}]▶[/bold {C_ORANGE}] "
                    f"[bold {C_CMD}]{cmd:<{CMD_COL}}[/bold {C_CMD}]"
                    f"[{C_DIM}]{desc}[/{C_DIM}]"
                )
            else:
                line = (
                    "  "
                    f"[{C_CMD}]{cmd:<{CMD_COL}}[/{C_CMD}]"
                    f"[{C_DIM}]{desc}[/{C_DIM}]"
                )
            lines.append(line)
        return "\n".join(lines)


class CompactRichLog(RichLog):
    """
    Claude / Codex CLI 風格對話區：回合制 transcript。

    每個回合 =
      1. write_user()  — 使用者提示（深底 + ›）
      2. agent stream  — 助手回覆（純文字串流）
    """

    CMD_COL = CMD_COL
    _agent_stream_line_count: int = 0

    def write_user(self, message: str) -> None:
        """使用者回合開始（類 Claude 已送出 prompt 樣式）。"""
        self.write(
            f"[on {C_INPUT_BG} {C_INPUT_TEXT}]› {message}[/on {C_INPUT_BG} {C_INPUT_TEXT}]"
        )

    def write_cmd(self, cmd: str, desc: str) -> None:
        self.write(
            f"[{C_CMD}]{cmd:<{self.CMD_COL}}[/{C_CMD}][{C_DIM}]{desc}[/{C_DIM}]"
        )

    def write_dim(self, message: str) -> None:
        self.write(f"[{C_DIM}]{message}[/{C_DIM}]")

    def write_error(self, message: str) -> None:
        self.write(f"[red]{message}[/red]")

    def write_system(self, message: str) -> None:
        """系統訊息（供 CommandCtx 使用）。"""
        self.write_dim(message)

    def write_assistant(self, message: str) -> None:
        """一般助手訊息（非串流時使用）。"""
        self.write(message)

    # ── Streaming 支援 ──────────────────────────────────────────

    def begin_agent_stream(self) -> None:
        """開始新的 agent 串流，寫一行空白佔位。"""
        self._agent_stream_line_count = 0
        self.write("")

    def append_agent_stream(self, full_text: str) -> None:
        """用 full_text 取代目前 agent 回覆的所有行。"""
        from rich.segment import Segment
        from rich.text import Text

        console = self.app.console
        render_width = max(
            self.scrollable_content_region.width,
            self.min_width,
        )

        renderable = (
            Text.from_markup(full_text) if self.markup else Text(full_text)
        )
        render_options = console.options.update_width(render_width)
        if not self.wrap:
            render_options = render_options.update(
                overflow="ignore", no_wrap=True
            )

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
        """串流結束後加一個空行作為分隔。"""
        self.write("")
        self._agent_stream_line_count = 0


class StatusBar(Static):
    """底部狀態列（Claude Code 風格：狀態 + 快捷鍵提示）。"""

    status = reactive("● 初始化中...")

    def render(self) -> str:
        return (
            f"  [{C_DIM}]{self.status}[/{C_DIM}]\n"
            f"  [{C_DIM}]enter send · tab complete · ctrl+l clear · ctrl+n new[/{C_DIM}]"
        )


class ThinkingLine(Static):
    """思考中提示列，顯示在輸入框上方分隔線之上。"""

    visible = reactive(False)
    label = reactive("✳ 思考中...")

    def render(self) -> str:
        if not self.visible:
            return ""
        return f"[{C_DIM}]{self.label}[/{C_DIM}]"


class RenAgentApp(App):
    """
    主 TUI 應用程式（Claude Code 佈局）：
      ┌ Welcome Card（永遠顯示）
      ├ Chat Log（對話區，佔滿剩餘高度）
      ├ Thinking Line（思考中動畫提示）
      ├ SlashMenu（/ 指令補全）
      ├ ❯ Input（橘灰邊框輸入框）
      └ StatusBar（模型 / 連線狀態 + 快捷鍵）
    """

    TITLE = "REN AGENT"
    CSS = f"""
    Screen {{
        layout: vertical;
        background: {C_BG};
    }}

    #hero-card {{
        layout: vertical;
        border: solid {C_ORANGE};
        border-title-align: left;
        border-title-color: {C_ORANGE};
        border-title-background: {C_BG};
        border-title-style: bold;
        padding: 1 0 1 0;
        margin: 1 1 0 1;
        height: auto;
        background: {C_BG};
    }}

    #hero-body {{
        layout: grid;
        grid-size: 2 1;
        grid-columns: 1fr 1fr;
        grid-gutter: 0;
        height: auto;
        min-height: 12;
    }}

    #hero-left {{
        column-span: 1;
        row-span: 1;
        width: 100%;
        height: 100%;
        layout: vertical;
        padding: 0 1;
        align: center middle;
    }}

    #hero-welcome {{
        width: auto;
        text-align: center;
        height: auto;
        margin: 0 0 1 9;
    }}

    #hero-mascot {{
        width: {MASCOT_WIDTH};
        min-width: {MASCOT_WIDTH};
        max-width: {MASCOT_WIDTH};
        height: {MASCOT_HEIGHT};
        min-height: {MASCOT_HEIGHT};
        text-align: left;
        text-wrap: nowrap;
        margin-bottom: 1;
    }}

    #hero-meta {{
        width: auto;
        text-align: center;
        height: auto;
        color: {C_DIM};
        margin: 0 0 1 5;
    }}

    #hero-right {{
        column-span: 1;
        row-span: 1;
        width: 100%;
        height: 100%;
        border-left: solid {C_ORANGE};
        padding: 0 2;
        layout: vertical;
    }}

    #hero-tips-title,
    #hero-activity-title {{
        color: {C_ORANGE};
        text-style: bold;
        height: auto;
        margin-bottom: 0;
    }}

    #hero-divider {{
        margin: 1 0;
        color: {C_ORANGE};
    }}

    #hero-tips,
    #hero-activity {{
        height: auto;
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
        height: auto;
        layout: horizontal;
        margin: 0 1;
        border: solid {C_BORDER};
        background: {C_INPUT_BG};
        padding: 0 1;
    }}

    #prompt-prefix {{
        width: 2;
        min-width: 2;
        color: {C_PLACEHOLDER};
        background: {C_INPUT_BG};
        content-align: left middle;
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
        padding: 0 0 1 0;
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
        # 佇列項目：(kind, content)，kind 為 "message" 或 "slash"
        self._pending_queue: list[tuple[str, str]] = []

        # v0.3.0：輸入 history + 最後回應時間
        self._input_history: list[str] = []
        self._input_history_index: int | None = None
        self._last_response_at: str | None = None

    # ── Widget helpers ───────────────────────────────────────────

    def _chat(self) -> CompactRichLog:
        return self.query_one("#chat-log", CompactRichLog)

    def _input(self) -> Input:
        return self.query_one("#user-input", Input)

    # ── Textual lifecycle ────────────────────────────────────────

    def compose(self) -> ComposeResult:
        with HeroCard(id="hero-card"):
            with Grid(id="hero-body"):
                with Vertical(id="hero-left"):
                    yield Static("[bold]Welcome back![/bold]", id="hero-welcome")
                    yield MascotArt(id="hero-mascot")
                    meta_text = (
                        f"{self.config.ollama.model} on Ollama\n"
                        "~/ren-agent"
                    )
                    yield Static(meta_text, id="hero-meta")
                with Vertical(id="hero-right"):
                    yield Static("Tips for getting started", id="hero-tips-title")
                    tips_text = (
                        f"[{C_DIM}]Run /help to see available commands[/]\n"
                        f"[{C_DIM}]Run /ros topics to inspect ROS2 topics[/]"
                    )
                    yield Static(tips_text, id="hero-tips")
                    yield Rule(line_style="solid", id="hero-divider")
                    yield Static("Recent activity", id="hero-activity-title")
                    yield Static(f"[{C_DIM}]No recent activity[/]", id="hero-activity")

        with Vertical(id="chat-panel"):
            yield CompactRichLog(
                id="chat-log",
                highlight=True,
                markup=True,
                wrap=True,
            )

        with Vertical(id="input-area"):
            yield ThinkingLine(id="thinking-line")
            yield SlashMenu(id="slash-menu")
            with Horizontal(id="prompt-zone"):
                yield Static("❯", id="prompt-prefix")
                yield Input(
                    placeholder="Ask a question...",
                    id="user-input",
                    compact=True,
                )

        yield StatusBar(id="status-bar")

    def on_mount(self) -> None:
        self.check_ollama()
        self._input().focus()

        # 註冊 Slash commands / Skills
        register_builtin_commands()
        register_ros2_skills()
        # set_model skill：讓 /model 走 Skill 介面
        register_skill(
            Skill(
                name="set_model",
                description="切換 Ollama 模型",
                func=self._set_model_skill,
            )
        )

    # ── Skill 實作 ───────────────────────────────────────────────

    async def _set_model_skill(self, name: str) -> str:
        """透過 Skill 介面切換模型（供 /model 使用）。"""
        name = name.strip()
        old_model = self.config.ollama.model
        if not name:
            return f"目前模型：{old_model}"
        self.config.ollama.model = name
        self.agent = OllamaAgent(config=self.config.ollama)
        self.agent.set_system_prompt(self.config.agent.system_prompt)
        status = self.query_one(StatusBar)
        status.status = f"● 已切換模型為 {name}"
        return f"模型已從 {old_model} 切換為 {name}"

    # ── 佇列 helper ────────────────────────────────────────────

    def _slash_cmd(self, raw: str) -> str:
        parts = raw[1:].strip().split()
        return parts[0].lower() if parts else ""

    def _format_queue_label(self) -> str:
        if not self._pending_queue:
            return ""
        labels: list[str] = []
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
        """把訊息或斜線指令排隊；若閒置則立刻執行。"""
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
        """完成一項工作後，接著處理佇列中的下一則。"""
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

    def _sanitize_llm_output(self, full_response: str) -> str:
        """去除模型常見的 Q:/A: 包裝前綴。"""
        stripped = full_response.lstrip()
        if stripped.startswith(("Q:", "Q：")):
            if "\nA:" in stripped:
                idx = stripped.index("\nA:")
                after = stripped[idx + len("\nA:") :]
                return after.lstrip("\n ").lstrip()
            if "\nA：" in stripped:
                idx = stripped.index("\nA：")
                after = stripped[idx + len("\nA：") :]
                return after.lstrip("\n ").lstrip()

        if stripped.startswith(("A:", "A：")):
            after = stripped[2:]
            return after.lstrip("\n ").lstrip()

        return full_response

    # ── SlashMenu 控制 ──────────────────────────────────────────

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
        """當 SlashMenu 開啟時移動選項，否則瀏覽上一筆輸入。"""
        menu = self.query_one("#slash-menu", SlashMenu)
        if "-visible" in menu.classes:
            menu.move_selection(-1)
            return
        self._history_prev()

    def action_slash_down(self) -> None:
        """當 SlashMenu 開啟時移動選項，否則瀏覽下一筆輸入。"""
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

    # ── Input history ───────────────────────────────────────────

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

    # ── Input 事件 ──────────────────────────────────────────────

    async def on_input_changed(self, event: Input.Changed) -> None:
        self._update_slash_menu(event.value)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        message = event.value.strip()
        if not message:
            return

        menu = self.query_one("#slash-menu", SlashMenu)

        # 如果 SlashMenu 開著，Enter 先補全，不送出
        if "-visible" in menu.classes:
            self.action_slash_complete()
            return

        event.input.clear()
        self._update_slash_menu("")

        # 記錄輸入 history
        self._input_history.append(message)
        self._input_history_index = None

        # 斜線指令：不進入對話回合，/bye 可立即執行
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
            # 未知指令：當一般訊息送給模型
            self._enqueue_message(message)
            return

        # 一般訊息：忙碌時排隊，輪到才顯示 › prompt 並串流回覆
        self._enqueue_message(message)

    # ── 狀態管理 ────────────────────────────────────────────────

    def _set_thinking(self, active: bool) -> None:
        line = self.query_one("#thinking-line", ThinkingLine)
        line.visible = active
        if active:
            line.add_class("-visible")
        else:
            line.remove_class("-visible")

    # ── Ollama 連線檢查 ─────────────────────────────────────────

    @work(thread=True)
    def check_ollama(self) -> None:
        status = self.query_one(StatusBar)
        ok = asyncio.run(self.agent.check_connection())
        if ok:
            msg = f"● 已連線 Ollama ({self.config.ollama.model})"
        else:
            msg = "✗ Ollama 未啟動 — 請執行: ollama serve"
        self.call_from_thread(setattr, status, "status", msg)

    # ── Streaming LLM 回覆（佇列版）──────────────────────────────

    @work(exclusive=True)
    async def stream_response(self, message: str) -> None:
        """一個對話回合：先顯示使用者 prompt，再串流助手回覆。"""
        self._thinking = True
        chat = self._chat()
        status = self.query_one(StatusBar)
        self._set_thinking(True)
        status.status = f"⟳ 思考中... · {self.config.ollama.model}"

        chat.write_user(message)
        full_response = ""
        chat.begin_agent_stream()

        try:
            async for token in self.agent.chat_stream(message):
                full_response += token
                chat.append_agent_stream(
                    self._sanitize_llm_output(full_response)
                )
            chat.end_agent_stream()
        except Exception as e:  # noqa: BLE001
            chat.write_error(f"串流錯誤：{e}")
        finally:
            self._last_response_at = datetime.now().strftime("%H:%M:%S")
            self._work_finished()

    @work(exclusive=True)
    async def execute_slash_command(self, raw: str) -> None:
        """執行佇列中的斜線指令。"""
        self._thinking = True
        self._set_thinking(True)
        status = self.query_one(StatusBar)
        status.status = f"⟳ 執行指令 {raw} · {self.config.ollama.model}"
        try:
            await self.handle_slash_command(raw)
        finally:
            self._work_finished()

    # ── 斜線指令（Registry + Skills 版）────────────────────────

    async def handle_slash_command(self, raw: str) -> bool:
        """處理以 / 開頭的指令，回傳是否已處理."""
        chat = self._chat()

        text = raw.lstrip("/")
        if not text:
            chat.write_system("空的指令。")
            return True

        parts = text.split(maxsplit=2)
        cmd = parts[0]
        sub = parts[1] if len(parts) > 1 else ""
        rest = parts[2] if len(parts) > 2 else ""

        # 特別處理 /ros topics /ros echo
        if cmd in ("ros", "ros2"):
            if sub == "topics":
                cmd_key = "ros-topics"
                args = ""
            elif sub == "echo":
                cmd_key = "ros-echo"
                args = rest
            else:
                chat.write_system("用法：/ros topics 或 /ros echo <topic>")
                return True
        else:
            cmd_key = cmd
            args = sub + (" " + rest if rest else "")

        command = get_command(cmd_key)
        if not command:
            chat.write_dim(
                f"未知指令：/{cmd_key}，視為一般訊息送給 Agent。"
            )
            return False  # 交給 LLM 處理

        ctx = self._CommandCtx(self)

        # 把原始輸入寫進 chat（讓你看得到自己打的指令）
        chat.write_user(raw)

        # /clear 先清畫面與歷史
        if cmd_key == "clear":
            chat.clear()
            self.agent.reset_history()
            self._pending_queue.clear()
            self._update_queue_status()

        await command.handler(ctx, args)
        return True

    # ── Action handlers ─────────────────────────────────────────

    def action_clear_chat(self) -> None:
        self._chat().clear()
        self.agent.reset_history()
        self._pending_queue.clear()
        self._update_queue_status()

    def action_new_session(self) -> None:
        self.action_clear_chat()

    # ── Command Context（給 core.commands 使用）─────────────────

    class _CommandCtx(CommandContext):
        def __init__(self, app: "RenAgentApp") -> None:
            self.app = app

        async def write_user(self, text: str) -> None:
            self.app._chat().write_user(text)

        async def write_assistant(self, text: str) -> None:
            self.app._chat().write_assistant(text)

        def write_system(self, text: str) -> None:
            self.app._chat().write_system(text)

        async def ask_llm(self, prompt: str) -> None:
            # 直接走 queue / streaming 流程
            self.app._enqueue_message(prompt)

        def exit_app(self) -> None:
            self.app.exit()

        async def run_skill(self, name: str, **kwargs) -> None:
            result = await core_run_skill(name, **kwargs)
            self.app._chat().write_system(result)