"""
ren-agent TUI — Claude Code 風格。

╔══════════════ 畫面結構 ══════════════╗
║                                       ║
║  Chat Log（首畫面有 welcome panel，  ║
║    開始對話後會被往上捲走）          ║
║                                       ║
║  Thinking Line — 思考中 spinner       ║
║  Slash Menu   — 補全選單              ║
║  > Input      — focus 時橘框          ║
║  Status Bar   — 狀態 + 快捷鍵         ║
║                                       ║
╚═══════════════════════════════════════╝

主要元件：
  - RenAgentApp        Textual App，組合所有 widget
  - CompactRichLog     對話區（支援 streaming 重畫）
  - SlashMenu          / 指令補全
  - ThinkingLine       spinner 動畫
  - StatusBar          底部狀態 + 提示

工作流程：
  on_input_submitted → 判斷 / 開頭 vs 一般訊息
    一般訊息 → _enqueue("message") → stream_response (worker)
    斜線指令 → 找 registry → handler(ctx, args)
              其中 handler 可能 ctx.run_skill(...) 跑 skill

  ESC：cancel_all 取消當前 worker，CancelledError 走 finally 收尾
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
# 想全 UI 改色從這裡改就好（被 CSS f-string 字串替換）
C_BG = "#1a1a1a"          # 背景（接近純黑）
C_ORANGE = "#d07d50"      # 主題橘（focus / banner / spinner）
C_CMD = "#a5b4fc"         # /help 指令名的淺紫
C_DIM = "#999999"         # 中灰（描述、hint 文字）
C_INPUT_BG = "#3a3a3a"    # 輸入框背景（比畫面背景亮）
C_INPUT_TEXT = "#ffffff"  # 輸入框文字
C_PLACEHOLDER = "#949494" # placeholder 文字
C_BORDER = "#606060"      # 未 focus 邊框

# Slash 補全選單裡，指令欄的對齊寬度
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

# Spinner 動畫的 4 個 frame（200ms 換一張）
_SPINNER_FRAMES = ("✳", "✦", "✶", "✺")

# 跨 session 持久化的輸入歷史
_HISTORY_FILE = DEFAULT_CONFIG_PATH.parent / "history.txt"
_HISTORY_MAX = 200    # 超過會 truncate


# ── History 檔案讀寫 ────────────────────────────────────
# 開場 welcome panel 需要顯示「最近 3 筆」；輸入後也會 append 一筆
# 失敗都吞掉 — 歷史記錄不是關鍵功能

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
        # 保留最後 _HISTORY_MAX 筆
        existing = existing[-_HISTORY_MAX:]
        _HISTORY_FILE.write_text("\n".join(existing) + "\n", encoding="utf-8")
    except Exception:
        pass


# ── Welcome Panel 組裝 ──────────────────────────────────
# 結構：
#   ┌─ REN AGENT vX.Y.Z ──────────────────────────────────┐
#   │           [置中 ASCII banner]                        │
#   │                                                      │
#   │  [mascot]                Tips for getting started    │
#   │  [meta]                  Recent activity             │
#   └──────────────────────────────────────────────────────┘
# 整框再用 Align.center 包起來 → 在終端寬度內水平置中

def _build_welcome_panel(model: str) -> Align:
    banner = Align.center(Text(_BANNER, style=f"bold {C_ORANGE}", no_wrap=True))
    # mascot 與 meta 都左 padding 2 格，跟右欄留視覺距離
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

    # 兩欄 50/50 grid（修改 ratio 可以調左右寬度）
    bottom = Table.grid(expand=True, padding=(0, 2))
    bottom.add_column(ratio=1)
    bottom.add_column(ratio=1)
    bottom.add_row(left, right)

    body = Group(banner, Text(""), bottom)

    # expand=False 讓 Panel 縮成內容寬，再 Align.center 才會視覺置中
    panel = Panel(
        body,
        title=f"[bold {C_ORANGE}]REN AGENT v{__version__}[/bold {C_ORANGE}]",
        title_align="left",
        border_style=C_ORANGE,
        padding=(1, 2),
        expand=False,
    )
    return Align.center(panel)


# ══════════ Widgets ══════════════════════════════════════

class SlashMenu(Static):
    """
    / 指令補全選單。
    輸入框打第一個字元 `/` 時出現；上下鍵移動、Tab/Enter 補全。
    """

    # reactive：屬性變動會自動 trigger render
    filter_text = reactive("")
    selected_index = reactive(0)

    def _matches(self) -> list[tuple[str, str]]:
        """根據 filter_text 過濾 registry 裡的指令。"""
        query = self.filter_text.lower().strip()
        if not query.startswith("/"):
            return []
        q = query[1:]   # 去掉開頭 /
        items: list[tuple[str, str]] = []
        for cmd in all_commands():
            # 主名稱或 alias 任一個 prefix match 都算
            if cmd.name.startswith(q) or any(a.startswith(q) for a in cmd.aliases):
                items.append((f"/{cmd.name}", cmd.description))
        return items

    def selected_cmd(self) -> str | None:
        """Tab/Enter 補全要用。"""
        matches = self._matches()
        if not matches:
            return None
        idx = max(0, min(self.selected_index, len(matches) - 1))
        return matches[idx][0]

    def move_selection(self, delta: int) -> None:
        """上下鍵改變選取（循環）。"""
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
    """
    對話 transcript 區。

    一般 write 都是 append-only；唯一例外是助手串流：
      begin_agent_stream → append_agent_stream(全文) × N → end_agent_stream
    每次 append 都用 _agent_stream_line_count 記住「現在這段佔了幾行」，
    下次 append 時刪掉舊行重畫，達到 live update 效果。
    """

    CMD_COL = CMD_COL
    _agent_stream_line_count: int = 0

    # ── 各種 write helper（不同類型訊息上不同色）──
    def write_user(self, message: str) -> None:
        """使用者送出的訊息：深色背景 + › 前綴。"""
        self.write(
            f"[on {C_INPUT_BG} {C_INPUT_TEXT}]› {message}[/on {C_INPUT_BG} {C_INPUT_TEXT}]"
        )

    def write_dim(self, message: str) -> None:
        self.write(f"[{C_DIM}]{message}[/{C_DIM}]")

    def write_error(self, message: str) -> None:
        self.write(f"[red]{message}[/red]")

    def write_system(self, message: str) -> None:
        """系統訊息（指令的提示、skill 結果）— 灰色。"""
        self.write_dim(message)

    def write_assistant(self, message: str) -> None:
        """非 streaming 的助手訊息。"""
        self.write(message)

    def write_tool_call(self, name: str, args: dict) -> None:
        """LLM 決定呼叫工具時顯示：→ tool_name({args}) ."""
        import json as _json
        args_str = _json.dumps(args, ensure_ascii=False)
        self.write(
            f"[{C_ORANGE}]→[/{C_ORANGE}] [{C_CMD}]{name}[/{C_CMD}]"
            f"[{C_DIM}]({args_str})[/{C_DIM}]"
        )

    def write_tool_result(self, name: str, result: str) -> None:
        """工具執行結果：第一行 ← 前綴，後續行縮排。"""
        first = result.splitlines()[0] if result else ""
        rest = result.splitlines()[1:] if result else []
        self.write(f"[{C_ORANGE}]←[/{C_ORANGE}] [{C_DIM}]{first}[/{C_DIM}]")
        for ln in rest:
            self.write(f"  [{C_DIM}]{ln}[/{C_DIM}]")

    # ── 助手 streaming 三部曲 ──
    def begin_agent_stream(self) -> None:
        """開始一段助手串流。寫一個空白佔位，等 append 時取代。"""
        self._agent_stream_line_count = 0
        self.write("")

    def append_agent_stream(self, full_text: str) -> None:
        """
        重畫助手回覆區塊。
        每次 streaming 收到新 token 都把整段 full_text 重新渲染：
          1. 用 Rich console render 把 markup 解析成 Strip 行
          2. 刪掉 RichLog.lines 末尾舊行（上次寫了幾行就刪幾行）
          3. 把新行 append，更新 virtual_size 與捲動位置
        這樣使用者看到的就是「逐字浮現」的效果。
        """
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

        # 刪掉上次寫的舊行
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
        """串流結束。寫一個空行做視覺分隔，counter 歸零。"""
        self.write("")
        self._agent_stream_line_count = 0


class StatusBar(Static):
    """
    底部狀態列。兩行：
      第 1 行：執行狀態（連線、思考中、佇列、最後回應時間）
      第 2 行：左快捷鍵提示、右快捷鍵提示
    """

    status = reactive("● 初始化中...")

    def render(self) -> str:
        hint_left = "/ for commands · ↑↓ history · tab to complete · esc to interrupt"
        hint_right = "ctrl+l clear · ctrl+c quit"
        return (
            f"  [{C_DIM}]{self.status}[/{C_DIM}]\n"
            f"  [{C_DIM}]{hint_left}[/{C_DIM}]"
            f"   [{C_DIM}]{hint_right}[/{C_DIM}]"
        )


class ThinkingLine(Static):
    """
    思考中 spinner（顯示在輸入框上方）。
    on_mount 每 200ms 換一個 frame；只在 active=True 才動。
    """

    active = reactive(False)
    _frame = 0

    def on_mount(self) -> None:
        # set_interval 是 Textual 內建的定時器
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
    """
    主 TUI App。

    重要 instance 屬性：
      self.config           AppConfig 單例（修改會反映到 skill）
      self.agent            OllamaAgent，每次切模型重建
      self._thinking        是否正在跑 worker（影響 _enqueue 行為）
      self._pending_queue   等待中的訊息/指令佇列（思考中時排隊）
      self._input_history   輸入歷史（持久化在 history.txt）
    """

    TITLE = "REN AGENT"

    # ── CSS（textual 的 stylesheet）──
    # f-string 注意：CSS 裡的 {{ 對應實際 {，{C_xxx} 是 Python 變數插值
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

    # ── 鍵盤快捷鍵 ────────────────────────────────────
    # priority=True 表示優先攔截（不會被 Input 吃掉）
    BINDINGS = [
        Binding("ctrl+c", "quit", "離開", priority=True),
        Binding("ctrl+l", "clear_chat", "清空對話", show=True),
        Binding("ctrl+n", "new_session", "新對話", show=True),
        Binding("escape", "interrupt", "中斷思考", show=False, priority=True),
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
        # 載入設定（單例），用 CLI 參數覆蓋預設模型/host
        self.config = get_config()
        self.config.ollama.model = model
        self.config.ollama.host = ollama_host
        # 建 LLM agent，灌 system prompt
        self.agent = OllamaAgent(config=self.config.ollama)
        self.agent.set_system_prompt(self.config.agent.system_prompt)

        # 工作狀態
        self._thinking = False
        # 佇列項目：(kind, content)
        #   kind = "message"（要送 LLM） or "slash"（要執行 / 指令）
        self._pending_queue: list[tuple[str, str]] = []

        # 輸入歷史（跨 session 持久化）
        self._input_history: list[str] = _load_recent_history(_HISTORY_MAX)
        self._input_history_index: int | None = None  # 上下鍵瀏覽時的游標
        self._last_response_at: str | None = None     # 最後一次 LLM 回應時間（給 status bar）

    # ── Widget 快速存取 ──────────────────────────────────
    def _chat(self) -> CompactRichLog:
        return self.query_one("#chat-log", CompactRichLog)

    def _input(self) -> Input:
        return self.query_one("#user-input", Input)

    # ── Compose（描述 widget 樹）─────────────────────────
    def compose(self) -> ComposeResult:
        """Textual 啟動時呼叫一次，把 widget 組起來。"""
        # 對話區（佔滿剩餘高度）
        with Vertical(id="chat-panel"):
            yield CompactRichLog(
                id="chat-log", highlight=True, markup=True, wrap=True,
            )

        # 下方輸入區
        with Vertical(id="input-area"):
            yield ThinkingLine(id="thinking-line")  # spinner
            yield SlashMenu(id="slash-menu")        # / 補全
            with Horizontal(id="prompt-zone"):
                yield Static(">", id="prompt-prefix")  # > 符號
                yield Input(
                    placeholder="Ask a question...",
                    id="user-input",
                    compact=True,
                )

        # 最底狀態列
        yield StatusBar(id="status-bar")

    def on_mount(self) -> None:
        """compose 後執行一次：註冊 skill、寫 welcome、檢查 Ollama。"""
        # 順序很重要：command/skill 要先註冊，welcome panel 顯示的 /help 才有東西
        register_builtin_commands()
        register_ros2_skills()
        register_drive_skills()
        register_goto_skills()
        # set_model 是 TUI-only skill（需要 self.agent，所以註冊在這裡）
        register_skill(
            Skill("set_model", "切換 Ollama 模型", self._set_model_skill)
        )

        # 開場 welcome panel — 寫進 chat-log 當第一筆
        # 後續對話會把它往上推（Claude Code 行為）
        chat = self._chat()
        chat.write(_build_welcome_panel(self.config.ollama.model))
        chat.write("")

        # 背景測 Ollama 連線（thread worker，不阻塞 mount）
        self.check_ollama()
        self._input().focus()
        self._refresh_focus_style()

    # ── Skill 實作 ───────────────────────────────────────

    async def _set_model_skill(self, name: str) -> str:
        """/model 對應的 skill：切換 Ollama 模型，並重建 agent。"""
        name = name.strip()
        old = self.config.ollama.model
        if not name:
            return f"目前模型：{old}"
        self.config.ollama.model = name
        # 重建 agent；舊的 history 直接捨棄（換模型 = 新對話）
        self.agent = OllamaAgent(config=self.config.ollama)
        self.agent.set_system_prompt(self.config.agent.system_prompt)
        self.query_one(StatusBar).status = f"● 已切換模型為 {name}"
        return f"模型已從 {old} 切換為 {name}"

    # ── 佇列管理 ─────────────────────────────────────────
    # 為什麼要佇列：思考中（@work exclusive 跑著）時，使用者送出的新訊息
    # 不能直接打斷，要排隊等上一回合完成後依序執行。
    # _drain_queue 在 _work_finished 末端呼叫，自動拉下一個項目跑。

    def _slash_cmd(self, raw: str) -> str:
        """從 /xxx yyy 取出 xxx（小寫）。"""
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
        """佇列入口。閒置時直接跑；忙碌時排隊。"""
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
        """_work_finished 末端呼叫；如果佇列還有東西，啟動下一項。"""
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
        """每個 worker 在 finally 呼叫；把 thinking 旗標關掉，drain 佇列。"""
        self._thinking = False
        self._set_thinking(False)
        self.refresh(layout=True)
        self._drain_queue()

    # ── SlashMenu 控制 ───────────────────────────────────

    def _update_slash_menu(self, value: str) -> None:
        """on_input_changed 時呼叫：value 是 / 開頭就顯示 menu。"""
        menu = self.query_one("#slash-menu", SlashMenu)
        if value.startswith("/"):
            menu.filter_text = value
            menu.selected_index = 0
            menu.add_class("-visible")
        else:
            menu.filter_text = ""
            menu.remove_class("-visible")

    def action_slash_up(self) -> None:
        """↑：menu 開著就移動選取，否則翻歷史。"""
        menu = self.query_one("#slash-menu", SlashMenu)
        if "-visible" in menu.classes:
            menu.move_selection(-1)
            return
        self._history_prev()

    def action_slash_down(self) -> None:
        """↓：同上。"""
        menu = self.query_one("#slash-menu", SlashMenu)
        if "-visible" in menu.classes:
            menu.move_selection(1)
            return
        self._history_next()

    def action_slash_complete(self) -> None:
        """Tab：把 menu 選的指令填回輸入框（加一個空白方便繼續打參數）。"""
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

    # ── 輸入歷史導覽 ─────────────────────────────────────
    # 設計：第一次按 ↑ 跳到最後一筆；繼續按往上；按 ↓ 往下，到底再按一次清空

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

    # ── Input 事件處理 ───────────────────────────────────

    async def on_input_changed(self, event: Input.Changed) -> None:
        """每次打字都重算 SlashMenu。"""
        self._update_slash_menu(event.value)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Enter 送出：判斷是 / 指令還是一般訊息。"""
        message = event.value.strip()
        if not message:
            return

        # 如果 menu 開著，Enter 當補全用（不送出）
        menu = self.query_one("#slash-menu", SlashMenu)
        if "-visible" in menu.classes:
            self.action_slash_complete()
            return

        event.input.clear()
        self._update_slash_menu("")

        # 記錄到 history（即時持久化）
        self._input_history.append(message)
        self._input_history_index = None
        _append_history(message)

        # ── 分流：/ 開頭 vs 一般訊息 ──
        if message.startswith("/"):
            # /bye 系列：不進佇列，立刻處理
            if self._slash_cmd(message) in ("bye", "exit", "quit"):
                await self.handle_slash_command(message)
                return
            # 思考中：排隊
            if self._thinking:
                self._enqueue_slash(message)
                return
            handled = await self.handle_slash_command(message)
            if handled:
                return
            # 未知指令 → fallback 當訊息送 LLM
            self._enqueue_message(message)
            return

        # 一般訊息（會走 LLM，可能 trigger tool calling）
        self._enqueue_message(message)

    # ── Focus / 視覺樣式 ─────────────────────────────────

    def _refresh_focus_style(self) -> None:
        """根據 Input 是否 focused 切換 prompt-zone 的 -focused class。"""
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
        """切換 spinner 顯示。"""
        line = self.query_one("#thinking-line", ThinkingLine)
        line.active = active
        if active:
            line.add_class("-visible")
        else:
            line.remove_class("-visible")

    # ── Ollama 連線檢查（背景 thread）─────────────────────

    @work(thread=True)
    def check_ollama(self) -> None:
        """thread worker（避免 mount 時阻塞）；用 call_from_thread 寫回 UI。"""
        status = self.query_one(StatusBar)
        ok = asyncio.run(self.agent.check_connection())
        if ok:
            msg = f"● 已連線 Ollama ({self.config.ollama.model})"
        else:
            msg = "✗ Ollama 未啟動 — 請執行: ollama serve"
        self.call_from_thread(setattr, status, "status", msg)

    # ── Streaming（主對話 + tool calling）─────────────────

    @work(exclusive=True)
    async def stream_response(self, message: str) -> None:
        """
        一個完整的對話回合。exclusive=True：新的 stream_response 會取消舊的。
        流程：
          1. 顯示 user prompt
          2. 開助手 stream（● 前綴）
          3. async for token → 重畫 stream block
          4. tool call 時：end_stream → 寫 → / ← → begin_stream
          5. 結束或 ESC 中斷 → finally _work_finished
        """
        self._thinking = True
        chat = self._chat()
        status = self.query_one(StatusBar)
        self._set_thinking(True)
        status.status = f"⟳ 思考中... · {self.config.ollama.model}"

        chat.write_user(message)
        # ── 助手回覆區塊 ──
        # 用 ● 前綴標記助手訊息（Claude Code 風）
        # 每段 streaming 文字都會帶這個前綴，append_agent_stream 會
        # 把整段重畫所以前綴不會掉
        prefix = f"[bold {C_ORANGE}]●[/bold {C_ORANGE}] "
        block_text = ""
        chat.begin_agent_stream()

        # tool call 期間中斷目前 stream block，秀 → 呼叫 / ← 結果，再重開
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
                chat.append_agent_stream(prefix + block_text)
            chat.end_agent_stream()
        except asyncio.CancelledError:
            # ESC 中斷 — 收尾畫面，再把 CancelledError 往外丟讓 Textual worker 結束
            chat.end_agent_stream()
            raise
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
        """
        解析 /xxx ... 並呼叫對應 handler。
        回傳 True 表示已處理；False 表示找不到指令（呼叫端會 fallback 給 LLM）。
        """
        chat = self._chat()
        text = raw.lstrip("/")
        if not text:
            chat.write_system("空的指令。")
            return True

        # 切成最多 3 段：cmd、sub（給 /ros xxx）、rest（剩餘參數）
        parts = text.split(maxsplit=2)
        cmd = parts[0].lower()
        sub = parts[1] if len(parts) > 1 else ""
        rest = parts[2] if len(parts) > 2 else ""

        # /ros <sub> ...  →  registry 裡叫 ros-<sub>
        # 這層 special case 是為了讓使用者打「/ros topics」而不是「/ros-topics」
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
        """Ctrl+L：清空對話與 LLM 歷史。"""
        self._chat().clear()
        self.agent.reset_history()
        self._pending_queue.clear()
        self._update_queue_status()

    def action_new_session(self) -> None:
        """Ctrl+N：等同清空對話。"""
        self.action_clear_chat()

    def action_interrupt(self) -> None:
        """ESC：取消當前思考 / tool call，清空佇列。
        Textual 會把 CancelledError 丟進 stream_response 的 async for，
        finally 區塊裡的 _work_finished() 會把狀態重置。
        """
        if not self._thinking and not self._pending_queue:
            return
        self.workers.cancel_all()
        self._pending_queue.clear()
        self._chat().write_dim("⎯ 已中斷")
        self._thinking = False
        self._set_thinking(False)
        self._update_queue_status()

    # ── CommandContext 實作 ──────────────────────────────
    # 給 core.commands 的 handler 用；只暴露需要的 API，
    # handler 看不到也動不到 widget 本體（方便測試）

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
            """直接寫 Rich 物件（Table、Panel 等）— /help 用。"""
            self.app._chat().write(obj)

        async def ask_llm(self, prompt: str) -> None:
            """從 handler 內把訊息丟回 LLM 流程（會走佇列）。"""
            self.app._enqueue_message(prompt)

        def exit_app(self) -> None:
            self.app.exit()

        async def run_skill(self, skill: str, **kwargs) -> None:
            try:
                result = await core_run_skill(skill, **kwargs)
            except Exception as e:  # noqa: BLE001
                result = f"skill `{skill}` 失敗：{e}"
            self.app._chat().write_system(result)
