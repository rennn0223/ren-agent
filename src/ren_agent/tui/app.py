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
from typing import Any, Callable

from rich import box
from rich.align import Align
from rich.console import Group
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.events import Resize
from textual.geometry import Size
from textual.reactive import reactive
from textual.strip import Strip
from textual.screen import ModalScreen
from textual.widgets import Button, Input, RichLog, Static

from ren_agent import __version__
from ren_agent.core.commands import (
    CommandContext,
    all_commands,
    get_command,
    register_builtin_commands,
)
from ren_agent.core.config import DEFAULT_CONFIG_PATH, current_model_label, get_config
from ren_agent.core.llm_provider import BaseLLMProvider, create_provider
from ren_agent.core.ollama_client import OllamaAgent  # 向後相容
from ren_agent.core.skills import (
    Skill,
    all_tools,
    register_skill,
    run_skill as core_run_skill,
)
from ren_agent.tools.drive import register_drive_skills
from ren_agent.tools.goto import register_goto_skills
from ren_agent.tools.ros2_skills import register_ros2_skills
from ren_agent.core.approvals import (
    has_pending as has_pending_approval,
    pending_description,
)
from ren_agent.core.safety_state import is_armed
from ren_agent.tools.safety import register_safety_skills


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

# 臘腸狗吉祥物（welcome 左欄）
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

# 只畫「欄與欄之間那條垂直線」的自訂 box（無外框、無橫線）。
# 每行 4 字元：左框 / 橫線 / 欄間分隔 / 右框；只有 cell 列放 │。
_VLINE_BOX = box.Box(
    "    \n"   # top
    "  │ \n"   # head
    "    \n"   # head_row
    "  │ \n"   # mid（cell 列）
    "    \n"   # row
    "    \n"   # foot_row
    "  │ \n"   # foot
    "    \n"   # bottom
)


def _build_welcome_panel(label: str) -> Panel:
    # ── 左欄：臘腸狗 + 歡迎詞 + 環境資訊（皆置中）──
    left = Group(
        Text(""),
        Align.center(Text("Welcome back!", style=f"bold {C_ORANGE}")),
        Text(""),
        Align.center(Text(_MASCOT, style=C_ORANGE, no_wrap=True)),
        Text(""),
        Align.center(Text(label, style=C_DIM)),
        Align.center(Text("~/ren-agent", style=C_DIM)),
        Text(""),
    )

    # ── 右欄：上手提示 → 細分隔線 → 最近活動 ──
    tips_title = Text("Tips for getting started", style=f"bold {C_ORANGE}")
    tips = Text.from_markup(
        f"[{C_DIM}]Run [/{C_DIM}][{C_CMD}]/help[/{C_CMD}]"
        f"[{C_DIM}] to see all commands[/{C_DIM}]\n"
        f"[{C_DIM}]Run [/{C_DIM}][{C_CMD}]/arm[/{C_CMD}]"
        f"[{C_DIM}] then [/{C_DIM}][{C_CMD}]/drive forward[/{C_CMD}]"
        f"[{C_DIM}] to move the car[/{C_DIM}]\n"
        f"[{C_DIM}]Run [/{C_DIM}][{C_CMD}]/goto 應科大樓[/{C_CMD}]"
        f"[{C_DIM}] to send a goal[/{C_DIM}]\n"
        f"[{C_DIM}]Press [/{C_DIM}][{C_CMD}]Ctrl+X[/{C_CMD}]"
        f"[{C_DIM}] for emergency stop[/{C_DIM}]\n"
        f"[#8a8782][i]Or just ask in natural language — the agent calls tools itself[/i][/#8a8782]"
    )

    activity_title = Text("Recent activity", style=f"bold {C_ORANGE}")
    recent = _load_recent_history(3)
    if recent:
        activity = Text("\n".join(recent), style=C_DIM)
    else:
        activity = Text.from_markup("[#8a8782][i](none yet)[/i][/#8a8782]")

    right = Group(
        tips_title,
        tips,
        Rule(style=C_DIM),
        activity_title,
        activity,
    )

    # 兩欄 + 中間垂直分隔線（_VLINE_BOX）
    # 左欄固定寬度（容得下臘腸狗最寬那行 32），右欄吃剩餘空間。
    # 注意：Panel/Table 都要 expand=True，否則 expand=False 的量測會把
    # no_wrap 的臘腸狗截頭（踩過的坑）。
    bottom = Table(
        box=_VLINE_BOX,
        show_header=False,
        expand=True,
        padding=(0, 2),
        pad_edge=False,
        border_style=C_DIM,
    )
    bottom.add_column(width=38)
    bottom.add_column(ratio=1)
    bottom.add_row(left, right)

    return Panel(
        bottom,
        title=f"[bold {C_ORANGE}]REN AGENT v{__version__}[/bold {C_ORANGE}]",
        title_align="left",
        border_style=C_ORANGE,
        box=box.ROUNDED,
        padding=(1, 2),
        expand=True,
    )


# ══════════ Widgets ══════════════════════════════════════

# ── API Key 輸入 Modal ──────────────────────────────────
class ApiKeyModal(ModalScreen):
    """輸入並測試第三方 LLM API Key 的 Modal。dismiss(key) 表示確認，dismiss(None) 表示取消。"""

    CSS = """
    ApiKeyModal {
        align: center middle;
    }
    #modal-box {
        width: 64;
        height: auto;
        background: #2a2a2a;
        border: round #d07d50;
        padding: 1 2;
    }
    #modal-title {
        text-style: bold;
        color: #d07d50;
        margin-bottom: 1;
    }
    #modal-hint {
        color: #999999;
        margin-bottom: 1;
    }
    #key-input {
        margin-bottom: 1;
    }
    #test-result {
        height: 1;
        margin-bottom: 1;
        color: #999999;
    }
    #modal-buttons {
        height: auto;
        align: right middle;
    }
    #modal-buttons Button {
        margin-left: 1;
    }
    """

    def __init__(
        self,
        provider_name: str,
        current_key: str = "",
        test_fn: "Callable[[str], Awaitable[tuple[bool, str]]] | None" = None,
    ):
        super().__init__()
        self._provider_name = provider_name
        self._current_key = current_key
        self._test_fn = test_fn

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-box"):
            yield Static(f"設定 {self._provider_name} API Key", id="modal-title")
            yield Static("輸入 API Key 後可先測試，或直接儲存。", id="modal-hint")
            yield Input(
                password=True,
                placeholder="貼上 API Key…",
                id="key-input",
                value=self._current_key,
            )
            yield Static("", id="test-result")
            with Horizontal(id="modal-buttons"):
                yield Button("測試", id="btn-test", variant="primary")
                yield Button("儲存", id="btn-save", variant="success")
                yield Button("取消", id="btn-cancel")

    def on_mount(self) -> None:
        self.query_one("#key-input", Input).focus()

    @work(exclusive=False)
    async def _run_test(self, key: str) -> None:
        result_label = self.query_one("#test-result", Static)
        result_label.update("⟳ 測試中…")
        if self._test_fn is None:
            result_label.update("[yellow]（無測試函式）[/yellow]")
            return
        ok, err = await self._test_fn(key)
        if ok:
            result_label.update("[green]✓ 連線成功[/green]")
        else:
            short = err[:80] + "…" if len(err) > 80 else err
            result_label.update(f"[red]✗ {short}[/red]")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id == "btn-test":
            key = self.query_one("#key-input", Input).value.strip()
            if key:
                self._run_test(key)
        elif btn_id == "btn-save":
            key = self.query_one("#key-input", Input).value.strip()
            self.dismiss(key or None)
        elif btn_id == "btn-cancel":
            self.dismiss(None)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)


class SlashMenu(Static):
    """
    / 指令補全選單。
    輸入框打第一個字元 `/` 時出現；上下鍵移動、Tab/Enter 補全。
    """

    # reactive：屬性變動會自動 trigger render
    filter_text = reactive("")
    selected_index = reactive(0)

    # 一次最多顯示幾列（與 CSS max-height 對齊）；指令多於此就捲動。
    MENU_ROWS = 8
    _win_start = 0   # 目前可視視窗的起始 index（捲動位置）

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
        total = len(matches)
        idx = max(0, min(self.selected_index, total - 1))

        # ── 計算可視視窗 ──
        # 指令數不超過 MENU_ROWS：全部顯示，沒有 footer。
        # 超過時：保留最後一列當 footer（捲動指示），其餘列當內容並讓選取維持可見。
        scrollable = total > self.MENU_ROWS
        content_rows = self.MENU_ROWS - 1 if scrollable else self.MENU_ROWS

        start = self._win_start
        if idx < start:
            start = idx
        elif idx >= start + content_rows:
            start = idx - content_rows + 1
        start = max(0, min(start, max(0, total - content_rows)))
        self._win_start = start

        window = matches[start:start + content_rows]
        lines = []
        for i, (cmd, desc) in enumerate(window):
            real = start + i
            cmd_pad = f"{cmd:<{CMD_COL}}"
            if real == idx:
                lines.append(
                    f"[on #2a2a2a][bold white]{cmd_pad}[/bold white]"
                    f"[{C_DIM}]{desc}[/{C_DIM}][/on #2a2a2a]"
                )
            else:
                lines.append(
                    f"[white]{cmd_pad}[/white]"
                    f"[{C_DIM}]{desc}[/{C_DIM}]"
                )

        if scrollable:
            up = "↑" if start > 0 else " "
            down = "↓" if start + content_rows < total else " "
            lines.append(
                f"[{C_DIM}]{up}{down}  {idx + 1}/{total}"
                f"  ·  ↑↓ 捲動 · tab 補全[/{C_DIM}]"
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

    # 開場 welcome panel 的重建函式；只要它還在（使用者尚未開始對話），
    # 終端 resize 時就 clear 重畫一次，讓 welcome 永遠水平置中。
    welcome_factory: "Callable[[], Any] | None" = None

    def on_resize(self, event: Resize) -> None:
        """終端尺寸改變時，若還停在 welcome 畫面就重畫以維持置中。"""
        super().on_resize(event)
        if self.welcome_factory is not None:
            self.clear()
            # expand=True：撐到整個對話區寬度，Align.center 才有空間置中
            self.write(self.welcome_factory(), expand=True)
            self.write("")

    # ── 各種 write helper（不同類型訊息上不同色）──
    def write_user(self, message: str) -> None:
        """使用者送出的訊息：深色背景 + › 前綴。"""
        # 使用者一開口就離開 welcome 畫面，停止 resize 重畫
        self.welcome_factory = None
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
        """非 streaming 的助手訊息（Markdown 渲染 + ● 前綴）。"""
        self.write(self._assistant_renderable(message))

    def _assistant_renderable(self, text: str):
        """
        助手回覆統一外觀：左邊一個橘色 ● bullet，右邊 Markdown 內容，
        用 Table.grid 做 hanging indent（Claude Code 風）。
        text 是模型原始輸出（Markdown），不是 Rich markup。
        """
        from rich.markdown import Markdown

        grid = Table.grid(padding=(0, 1))
        grid.add_column(width=1, no_wrap=True)   # bullet 欄
        grid.add_column(ratio=1)                 # 內容欄（會 wrap）
        bullet = Text("●", style=f"bold {C_ORANGE}")
        content = Markdown(text) if text.strip() else Text("")
        grid.add_row(bullet, content)
        return grid

    def _render_to_strips(self, renderable) -> list[Strip]:
        """把任意 Rich renderable 轉成 RichLog 的 Strip 行清單。"""
        from rich.segment import Segment

        console = self.app.console
        render_width = max(self.scrollable_content_region.width, self.min_width)
        options = console.options.update_width(render_width)
        if not self.wrap:
            options = options.update(overflow="ignore", no_wrap=True)
        segments = console.render(renderable, options)
        strips = [Strip(list(s)) for s in Segment.split_lines(segments)]
        if not strips:
            strips = [Strip.blank(render_width)]
        return strips

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
        重畫助手回覆區塊（Markdown live render）。
        每次 streaming 收到新 token 都把整段 full_text 當 Markdown 重新渲染：
          1. 用 _assistant_renderable 包成 ● + Markdown grid，render 成 Strip 行
          2. 刪掉 RichLog.lines 末尾舊行（上次寫了幾行就刪幾行）
          3. 把新行 append，更新 virtual_size 與捲動位置
        這樣使用者看到的就是「逐字浮現 + 即時格式化」的效果。
        full_text 是模型原始輸出（Markdown），不含 Rich markup 前綴。
        """
        new_strips = self._render_to_strips(self._assistant_renderable(full_text))

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

    def on_mount(self) -> None:
        # 每 0.5s 刷新一次，讓 ARMED/DISARMED 徽章即時反映安全閂狀態
        # （arm/disarm/E-stop 都在 widget 外改狀態，這裡輪詢最簡單可靠）
        self.set_interval(0.5, self.refresh)

    def render(self) -> str:
        hint_left = "/ for commands · ↑↓ history · tab to complete · esc to interrupt"
        hint_right = "ctrl+x E-STOP · ctrl+l clear · ctrl+c quit"
        if is_armed():
            badge = "[#000000 on #d07d50] ● ARMED [/]"
        else:
            badge = "[#ffffff on #707070] ● DISARMED [/]"
        pending = "  [#000000 on #e0b000] ⏳ 待批准 /approve [/]" if has_pending_approval() else ""
        return (
            f"  {badge}{pending}  [{C_DIM}]{self.status}[/{C_DIM}]\n"
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

    #approval-card {{
        height: auto;
        margin: 0 1 1 1;
        padding: 0 1;
        border: round #e0b000;
        background: {C_INPUT_BG};
        display: none;
    }}

    #approval-card.-visible {{
        display: block;
    }}

    #approval-text {{
        height: auto;
        color: #e0b000;
        padding: 0 0 1 0;
    }}

    #approval-actions {{
        height: auto;
        align: left middle;
    }}

    #btn-approve, #btn-reject {{
        height: 1;
        min-width: 8;
        border: none;
        margin: 0 2 0 0;
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
        Binding("ctrl+x", "estop", "緊急停止 E-STOP", show=True, priority=True),
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
        # 建 LLM agent（依 current_provider 選 provider），灌 system prompt
        self.agent: BaseLLMProvider = create_provider(self.config)
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
        # 待批准卡片目前的顯示狀態（避免每次輪詢都重畫）
        self._approval_shown = False
        self._approval_desc = ""

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
            # 待批准卡片（像 Claude/Cursor 的批准按鈕）；預設隱藏
            with Vertical(id="approval-card"):
                yield Static("", id="approval-text")
                with Horizontal(id="approval-actions"):
                    yield Button("✓ 批准", id="btn-approve", variant="success")
                    yield Button("✗ 拒絕", id="btn-reject", variant="error")
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
        register_safety_skills()
        # set_model 是 TUI-only skill（需要 self.agent，所以註冊在這裡）
        register_skill(
            Skill("set_model", "切換 LLM 模型（ollama/openai/anthropic）", self._set_model_skill)
        )

        # 開場 welcome panel — 寫進 chat-log 當第一筆
        # 後續對話會把它往上推（Claude Code 行為）
        chat = self._chat()
        # expand=True：撐到整個對話區寬度，Align.center 才有空間置中
        chat.write(_build_welcome_panel(current_model_label(self.config)), expand=True)
        chat.write("")
        # 記住怎麼重建 welcome；終端 resize 時 CompactRichLog 會用它重畫保持置中
        chat.welcome_factory = lambda: _build_welcome_panel(current_model_label(self.config))

        # 背景測 Ollama 連線（thread worker，不阻塞 mount）
        self.check_ollama()
        # 背景暖 /cmd_vel publisher：避免 on_unmount 時才第一次建 publisher，
        # DDS discovery 來不及做完就被 destroy，fail-safe 停車根本送不出去。
        self._warm_ros_publishers()
        self._input().focus()
        self._refresh_focus_style()
        # 輪詢待批准狀態，有就彈出批准卡片（approval 由 widget 外部設定，輪詢最可靠）
        self.set_interval(0.4, self._refresh_approval_card)

    @work(thread=True, exclusive=False, group="ros-warm")
    def _warm_ros_publishers(self) -> None:
        """在背景 thread 預建關鍵 publisher，讓 DDS 完成 discovery。
        失敗（ROS2 未 source）就靜默跳過，TUI 不應該因此卡住。"""
        try:
            from ren_agent.tools.ros2_node import safe_get_ros2
            ros, _err = safe_get_ros2()
            if ros is None:
                return
            cfg = self.config
            ros.warm_publisher(cfg.ros2.cmd_vel_topic, "geometry_msgs/msg/Twist")
        except Exception:
            pass

    def on_unmount(self) -> None:
        """關閉前：① fail-safe 送停車 ② 乾淨關閉 ROS2（避免 C++ std::terminate）。"""
        try:
            from ren_agent.tools.safety import stop_now
            stop_now()
        except Exception:  # noqa: BLE001
            pass
        try:
            from ren_agent.tools.ros2_node import shutdown_ros2
            shutdown_ros2()
        except Exception:  # noqa: BLE001
            pass

    # ── Skill 實作 ───────────────────────────────────────

    # ── _set_model_skill helpers ──────────────────────────

    def _rebuild_agent(self) -> None:
        """重建 agent（換 provider/model 後呼叫）；舊 history 捨棄。"""
        self.agent = create_provider(self.config)
        self.agent.set_system_prompt(self.config.agent.system_prompt)
        label = current_model_label(self.config)
        self.query_one(StatusBar).status = f"● 已切換模型為 {label}"
        self.config.save_yaml(DEFAULT_CONFIG_PATH)

    async def _switch_ollama(self, model: str) -> str:
        from ren_agent.core.ollama_client import OllamaProvider
        tmp = OllamaProvider(self.config.ollama)
        ok, err = await tmp.validate_model(model)
        if not ok:
            return f"❌ {err}"
        old = current_model_label(self.config)
        self.config.ollama.model = model
        self.config.current_provider = "ollama"
        self._rebuild_agent()
        return f"模型已從 {old} 切換為 {model}（Ollama）"

    async def _switch_openai(self, model: str) -> str:
        try:
            from ren_agent.core.openai_provider import OpenAIProvider
        except ImportError:
            return "❌ openai package 未安裝。請執行：pip install openai"

        # 沒有 key 時彈 Modal
        if not self.config.openai.api_key:
            async def _test(key: str) -> tuple[bool, str]:
                from ren_agent.core.openai_provider import OpenAIProvider as _P
                from ren_agent.core.config import OpenAIConfig
                cfg = OpenAIConfig(api_key=key, base_url=self.config.openai.base_url, model=model)
                return await _P(cfg).check_connection()

            key = await self.push_screen_wait(ApiKeyModal("OpenAI", "", _test))
            if not key:
                return "已取消"
            self.config.openai.api_key = key

        # 驗證
        self.config.openai.model = model
        ok, err = await OpenAIProvider(self.config.openai).check_connection()
        if not ok:
            self.config.openai.api_key = ""
            return f"❌ OpenAI API Key 驗證失敗：{err}"

        old = current_model_label(self.config)
        self.config.current_provider = "openai"
        self._rebuild_agent()
        return f"模型已從 {old} 切換為 {model}（OpenAI）"

    async def _switch_anthropic(self, model: str) -> str:
        try:
            from ren_agent.core.anthropic_provider import AnthropicProvider
        except ImportError:
            return "❌ anthropic package 未安裝。請執行：pip install anthropic"

        if not self.config.anthropic.api_key:
            async def _test(key: str) -> tuple[bool, str]:
                from ren_agent.core.anthropic_provider import AnthropicProvider as _P
                from ren_agent.core.config import AnthropicConfig
                cfg = AnthropicConfig(api_key=key, model=model)
                return await _P(cfg).check_connection()

            key = await self.push_screen_wait(ApiKeyModal("Anthropic", "", _test))
            if not key:
                return "已取消"
            self.config.anthropic.api_key = key

        self.config.anthropic.model = model
        ok, err = await AnthropicProvider(self.config.anthropic).check_connection()
        if not ok:
            self.config.anthropic.api_key = ""
            return f"❌ Anthropic API Key 驗證失敗：{err}"

        old = current_model_label(self.config)
        self.config.current_provider = "anthropic"
        self._rebuild_agent()
        return f"模型已從 {old} 切換為 {model}（Anthropic）"

    async def _list_models(self) -> str:
        """列出目前設定 + 可用 Ollama 模型。"""
        from ren_agent.core.ollama_client import OllamaProvider
        tmp = OllamaProvider(self.config.ollama)
        ok, err = await tmp.check_connection()
        if ok:
            from ollama import AsyncClient
            resp = await AsyncClient(host=self.config.ollama.host).list()
            names = [m.model for m in resp.models]
            ollama_part = "  " + "\n  ".join(names) if names else "  （無已下載模型）"
        else:
            ollama_part = f"  ✗ 無法連線：{err}"

        openai_status = "✓ 已設定" if self.config.openai.api_key else "✗ 未設定 API Key"
        anthropic_status = "✓ 已設定" if self.config.anthropic.api_key else "✗ 未設定 API Key"
        current = current_model_label(self.config)

        return (
            f"目前：{current}\n\n"
            f"Ollama 本地模型（{self.config.ollama.host}）：\n{ollama_part}\n\n"
            f"OpenAI  — {openai_status}（目前模型：{self.config.openai.model}）\n"
            f"Anthropic — {anthropic_status}（目前模型：{self.config.anthropic.model}）\n\n"
            "切換方式：/model ollama:qwen3:8b  /model openai:gpt-4o  /model anthropic:claude-sonnet-4-6\n"
            "列表：/model list"
        )

    async def _set_model_skill(self, name: str) -> str:
        """/model 對應的 skill：支援 ollama/openai/anthropic，provider:model 格式。"""
        name = name.strip()
        if not name:
            return f"目前模型：{current_model_label(self.config)}"
        if name == "list":
            return await self._list_models()

        # 解析 provider:model（e.g. "openai:gpt-4o"；無前綴視為 ollama）
        provider, _, model = name.partition(":")
        if provider not in {"ollama", "openai", "anthropic"}:
            # 向後相容：沒有 provider 前綴，整段視為 ollama model
            provider, model = "ollama", name

        if provider == "openai":
            return await self._switch_openai(model)
        if provider == "anthropic":
            return await self._switch_anthropic(model)
        return await self._switch_ollama(model)

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
        base = current_model_label(self.config)
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
        """on_input_changed 時呼叫：只在「還在打指令名稱」階段顯示 menu。

        一旦輸入空白（代表指令已選好、開始打參數，如 `/goto 機械系館`），
        就收起選單，Enter 才會正常送出而不是被導去補全。
        """
        menu = self.query_one("#slash-menu", SlashMenu)
        if value.startswith("/") and " " not in value:
            menu.filter_text = value
            menu.selected_index = 0
            menu._win_start = 0
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

        # 只有當 menu 開著「且確實有可補全的指令」時，Enter 才當補全用；
        # 否則照常送出，避免卡在無法 enter 的狀態
        menu = self.query_one("#slash-menu", SlashMenu)
        if "-visible" in menu.classes and menu.selected_cmd() is not None:
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
            slash = self._slash_cmd(message)
            # /bye 系列：不進佇列，立刻處理
            if slash in ("bye", "exit", "quit"):
                await self.handle_slash_command(message)
                return
            # /estop、/stop：最高優先級，等同 Ctrl+X。
            # 不能讓使用者打的緊急停止排在 LLM 思考佇列後面。
            if slash in ("estop", "stop"):
                self._chat().write_user(message)
                self.action_estop()
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
        ok, err = asyncio.run(self.agent.check_connection())
        label = current_model_label(self.config)
        if ok:
            msg = f"● 已連線 {label}"
        else:
            provider = self.config.current_provider
            if provider == "ollama":
                msg = "✗ Ollama 未啟動 — 請執行: ollama serve"
            else:
                msg = f"✗ {label} 連線失敗：{err[:60]}"
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
        status.status = f"⟳ 思考中... · {current_model_label(self.config)}"

        chat.write_user(message)
        # ── 助手回覆區塊 ──
        # ● 前綴 + Markdown 渲染由 append_agent_stream 內部負責（Claude Code 風），
        # 這裡只要餵模型原始 Markdown 文字即可。
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
                chat.append_agent_stream(block_text)
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
            f"⟳ 執行 {raw} · {current_model_label(self.config)}"
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

        # handler 任何未捕捉的例外都不能把 Textual app 弄死（噴回 terminal）。
        # 之前 `/drive forward for 2` 之類打錯參數會直接讓 TUI crash。
        try:
            await command.handler(ctx, args)
        except Exception as e:  # noqa: BLE001
            chat.write_system(f"指令執行錯誤：{type(e).__name__}: {e}")
        return True

    # ── 待批准卡片（批准按鈕）──────────────────────────────

    def _refresh_approval_card(self) -> None:
        """輪詢 approvals 狀態：有待批准且非思考中就顯示卡片，否則收起。"""
        show = has_pending_approval() and not self._thinking
        desc = pending_description() or ""
        if show == self._approval_shown and desc == self._approval_desc:
            return
        self._approval_shown = show
        self._approval_desc = desc
        card = self.query_one("#approval-card")
        if show:
            self.query_one("#approval-text", Static).update(
                f"⏳ 此動作需人工批准：[white]{desc}[/white]"
            )
            card.add_class("-visible")
        else:
            card.remove_class("-visible")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """批准 / 拒絕按鈕：等同於打 /approve、/reject。"""
        if event.button.id not in ("btn-approve", "btn-reject"):
            return
        # 點下立刻收卡片，回饋更即時；實際結果由 worker 寫回對話
        self.query_one("#approval-card").remove_class("-visible")
        self._approval_shown = False
        self._approval_desc = ""
        raw = "/approve" if event.button.id == "btn-approve" else "/reject"
        self.execute_slash_command(raw)
        self._input().focus()

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

    def action_estop(self) -> None:
        """Ctrl+X：緊急停止 — 取消所有思考/串流 + 立即送 0 速度。

        E-stop 優先級最高：先 cancel_all 停掉 LLM 串流與佇列，
        再用獨立 worker（不會被 cancel_all 波及，因為在其之後建立）送停車指令。
        """
        self.workers.cancel_all()
        self._pending_queue.clear()
        self._thinking = False
        self._set_thinking(False)
        self._update_queue_status()
        self._chat().write_error("🛑 緊急停止 E-STOP — 送出停車指令中…")
        self._run_estop()

    @work(exclusive=False, group="estop")
    async def _run_estop(self) -> None:
        """獨立 worker 跑 estop skill，避免被一般思考佇列卡住。"""
        try:
            result = await core_run_skill("estop")
        except Exception as e:  # noqa: BLE001
            result = f"E-stop 失敗：{e}"
        self._chat().write_error(result)

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
