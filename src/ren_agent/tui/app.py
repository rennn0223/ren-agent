"""
ren-agent TUI 主介面
使用 Textual 框架，架構類似網頁前端：
  - CSS 控制版面和顏色
  - Widget 是 UI 元件（像 HTML 的 div）
  - reactive 變數改變時自動更新畫面
  - work decorator 讓耗時工作在背景執行，不卡住 UI
"""
from textual.app import App, ComposeResult     # App = 整個應用程式的根類別
from textual.binding import Binding            # 定義鍵盤快捷鍵
from textual.widgets import Header, Footer, Input, RichLog, Static, Label
from textual.containers import Horizontal, Vertical   # 排版容器，像 CSS flexbox
from textual.reactive import reactive          # reactive 變數：改變時自動觸發畫面更新
from textual import work                       # @work 裝飾器：把函式丟到背景執行緒/協程

from ren_agent.core.config import get_config
from ren_agent.core.ollama_client import OllamaAgent


# ASCII Art Banner，顯示在對話區頂部
BANNER = """\
[bold cyan]
██████╗ ███████╗███╗   ██╗      █████╗  ██████╗ ███████╗███╗   ██╗████████╗
██╔══██╗██╔════╝████╗  ██║     ██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝
██████╔╝█████╗  ██╔██╗ ██║     ███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║   
██╔══██╗██╔══╝  ██║╚██╗██║     ██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║   
██║  ██║███████╗██║ ╚████║     ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║   
╚═╝  ╚═╝╚══════╝╚═╝  ╚═══╝     ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝   
[/bold cyan][dim]v0.1.0 — Automotive AI Agent[/dim]
"""

# 長長臘腸狗 ASCII，顯示在 BANNER 下方，整隻塗滿粗體青色
# 側面長臘腸狗 ASCII，顯示在 BANNER 下方，整隻塗滿粗體青色
DACHSHUND = r"""
[bold cyan]
    ,                      ," e`--o
    ((                     (  | __,'
 \\~--------------------\_;/
 (                       /
  /) ._______________.  )
 (( (                (( (
  ``-'                ``-'
[/bold cyan]
"""


class StatusBar(Static):
    """
    底部狀態列元件。
    reactive 變數 status 改變時，render() 會自動重新執行更新畫面。
    """
    status = reactive("● 初始化中...")

    def render(self) -> str:
        return f"[dim]{self.status}[/dim]"


class RenAgentApp(App):
    """
    主 TUI 應用程式。
    版面：左側 Sidebar（功能選單）+ 右側對話區
    """

    # Textual 的 CSS（語法跟網頁 CSS 很像）
    CSS = """
    Screen {
        layout: vertical;
    }
    /* 主要區域：sidebar + 對話區左右排列 */
    #main-layout {
        layout: horizontal;
        height: 1fr;        /* 1fr = 佔滿剩餘空間 */
    }
    /* 左側 Sidebar */
    #sidebar {
        width: 26;          /* 固定 26 個字元寬 */
        background: $surface;
        border-right: solid $primary;
        padding: 1;
    }
    #sidebar-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    /* 右側對話區 */
    #chat-panel {
        width: 1fr;
        layout: vertical;
    }
    /* 對話記錄顯示區 */
    #chat-log {
        height: 1fr;
        border: solid $primary;
        margin: 0 1;
        padding: 0 1;
    }
    /* 輸入框區域 */
    #input-area {
        height: auto;
        padding: 0 1 1 1;
    }
    #user-input {
        border: solid $accent;
    }
    /* 底部狀態列 */
    #status-bar {
        height: 1;
        background: $surface;
        padding: 0 1;
    }
    #banner {
        margin: 0;
        text-align: center;
        height: auto;
    }
    .sidebar-item {
        padding: 0 1;
        height: 2;
    }
    .sidebar-item:hover {
        background: $primary 30%;
    }
    /* BANNER 底下的臘腸狗 */
    #mascot-main {
        height: auto;
        text-align: center;
        margin-top: 0;
        margin-bottom: 1;
    }
    """

    # 鍵盤快捷鍵定義，會顯示在底部 Footer
    BINDINGS = [
        Binding("ctrl+c", "quit", "離開", priority=True),
        Binding("ctrl+l", "clear_chat", "清空對話", show=True),
        Binding("ctrl+n", "new_session", "新對話", show=True),
        Binding("f1", "toggle_sidebar", "側欄", show=True),
    ]

    def __init__(self, model: str = "qwen3.6:35b", ollama_host: str = "http://localhost:11434"):
        super().__init__()
        self.config = get_config()
        # 用 CLI 傳進來的參數覆蓋設定檔的值
        self.config.ollama.model = model
        self.config.ollama.host = ollama_host
        # 建立 OllamaAgent 實例
        self.agent = OllamaAgent(config=self.config.ollama)
        self.agent.set_system_prompt(self.config.agent.system_prompt)
        # 防止使用者在 AI 還在回應時又送出訊息
        self._thinking = False

    def compose(self) -> ComposeResult:
        """
        定義 UI 結構，類似 HTML 的 DOM 結構。
        yield 每個 Widget 代表把它加進畫面。
        """
        yield Header(show_clock=True)    # 頂部標題列，顯示時鐘
        with Horizontal(id="main-layout"):
            # 左側 Sidebar
            with Vertical(id="sidebar"):
                yield Label("[bold]⚡ ren-agent[/bold]", id="sidebar-title")
                yield Static("📡 ROS2 Topics", classes="sidebar-item")
                yield Static("🚗 Navigation", classes="sidebar-item")
                yield Static("🛡️  Safety", classes="sidebar-item")
                yield Static("⚙️  Config", classes="sidebar-item")
                yield Static("─" * 22)
                yield Static(f"🤖 {self.config.ollama.model}", classes="sidebar-item")
                yield Static("─" * 22)
                yield Static("[dim]Ctrl+L  清空對話[/dim]", classes="sidebar-item")
                yield Static("[dim]Ctrl+N  新對話[/dim]", classes="sidebar-item")
                yield Static("[dim]F1      收合側欄[/dim]", classes="sidebar-item")
            # 右側對話區
            with Vertical(id="chat-panel"):
                # 上方 REN AGENT 大字
                yield Static(BANNER, id="banner")
                # 臘腸狗吉祥物，放在大字下面
                yield Static(DACHSHUND, id="mascot-main")
                # RichLog = 支援 Rich markup 的滾動文字區域
                yield RichLog(id="chat-log", highlight=True, markup=True, wrap=True)
                with Vertical(id="input-area"):
                    yield Input(
                        placeholder="輸入訊息... (Enter 送出)",
                        id="user-input",
                    )
        yield StatusBar(id="status-bar")
        yield Footer()    # 底部快捷鍵提示列

    def on_mount(self) -> None:
        """
        on_mount 在所有 Widget 都畫好之後才執行，
        類似網頁的 DOMContentLoaded 事件。
        """
        self.check_ollama()   # 背景檢查 Ollama 連線
        chat_log = self.query_one("#chat-log", RichLog)
        chat_log.write("[dim]歡迎使用 ren-agent！輸入任何訊息開始對話。[/dim]")
        # 讓輸入框自動取得焦點，使用者可以直接打字
        self.query_one("#user-input", Input).focus()

    @work(thread=True)   # thread=True = 在背景執行緒跑，不阻塞 UI
    def check_ollama(self) -> None:
        """背景執行：檢查 Ollama 是否在線，結果更新到狀態列"""
        import asyncio
        status = self.query_one(StatusBar)
        ok = asyncio.run(self.agent.check_connection())
        if ok:
            # 從背景執行緒安全地更新 UI
            self.call_from_thread(
                setattr,
                status,
                "status",
                f"● 已連線 Ollama ({self.config.ollama.model})",
            )
        else:
            self.call_from_thread(
                setattr,
                status,
                "status",
                "✗ Ollama 未啟動 — 請執行: ollama serve",
            )

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """
        當使用者按下 Enter，這個事件處理器就會被呼叫。
        """
        message = event.value.strip()    # 去掉頭尾空白

        # 空訊息或 AI 還在思考時，忽略這次輸入
        if not message or self._thinking:
            return

        # 先清空輸入框，體驗比較好
        event.input.clear()

        # 如果是斜線開頭，先當作指令處理
        if message.startswith("/"):
            handled = await self.handle_slash_command(message)
            if handled:
                # 已經處理完，不要再丟給 LLM
                return

        # 一般聊天訊息
        chat_log = self.query_one("#chat-log", RichLog)
        chat_log.write(f"\n[bold green]你:[/bold green] {message}")

        # 丟給 LLM 並顯示回應
        self.stream_response(message)

    async def handle_slash_command(self, raw: str) -> bool:
        """
        處理以 / 開頭的指令，不送去 LLM。
        回傳 True = 已處理，False = 不認得這個指令（交給 LLM 處理）。
        """
        chat_log = self.query_one("#chat-log", RichLog)
        status = self.query_one(StatusBar)

        # 拿掉開頭的 /，拆成「指令 + 參數」
        parts = raw[1:].strip().split()   # "/model qwen3:8b" -> ["model", "qwen3:8b"]
        if not parts:
            return False

        cmd = parts[0].lower()
        args = parts[1:]

        if cmd in ("bye", "exit", "quit"):
            # 在畫面上留個紀錄，然後關閉應用程式
            chat_log.write("\n[bold magenta]/bye[/bold magenta]")
            chat_log.write("結束對話，正在關閉 ren-agent ...")
            self.exit()
            return True

        if cmd in ("clear", "cls"):
            self.action_clear_chat()
            return True

        if cmd == "model" and args:
            # 變更目前使用的模型，例如：/model qwen3:8b
            new_model = args[0]
            old_model = self.config.ollama.model

            self.config.ollama.model = new_model
            # 重建 OllamaAgent，讓新模型生效
            from ren_agent.core.ollama_client import OllamaAgent as _OllamaAgent
            self.agent = _OllamaAgent(config=self.config.ollama)
            self.agent.set_system_prompt(self.config.agent.system_prompt)

            chat_log.write(f"\n[bold magenta]/model[/bold magenta] {old_model} → {new_model}")
            status.status = f"● 已切換模型為 {new_model}"
            return True

        if cmd == "help":
            chat_log.write("\n[bold magenta]可用斜線指令：[/bold magenta]")
            chat_log.write("/bye        結束並關閉 ren-agent")
            chat_log.write("/clear      清空對話記錄")
            chat_log.write("/model X    切換模型，例如 /model qwen3:8b")
            chat_log.write("/help       顯示這個說明")
            return True

        # 不認識的指令，就當一般訊息交給 LLM 處理
        chat_log.write(f"\n[dim]未知指令：{raw}，當一般訊息送給 Agent。[/dim]")
        return False

    @work(exclusive=True)   # exclusive=True = 同時只能跑一個，防止重複送出
    async def stream_response(self, message: str) -> None:
        """
        非同步背景工作：向 Ollama 發送訊息，收集完整回應後一次寫入畫面。
        RichLog.write(content, ...) 只接受 content 等少數參數，不能傳 end / markup。 [Textual docs]
        """
        self._thinking = True
        chat_log = self.query_one("#chat-log", RichLog)
        status = self.query_one(StatusBar)
        status.status = "⟳ 思考中..."

        # 用來累積本次回應的所有文字
        full_response = ""

        try:
            # 從 Ollama 串流拿 token，全部接成一條長字串
            async for token in self.agent.chat_stream(message):
                full_response += token

            # 先寫出 Agent 標題行
            chat_log.write("[bold cyan]Agent:[/bold cyan]")
            # 再寫出完整回應內容
            chat_log.write(full_response)
            # 空行分隔上下對話
            chat_log.write("")
        finally:
            # 不管成功或失敗，都要把狀態改回「就緒」
            self._thinking = False
            status.status = f"● 就緒 ({self.config.ollama.model})"

    def action_clear_chat(self) -> None:
        """快捷鍵 Ctrl+L：清空對話記錄"""
        chat_log = self.query_one("#chat-log", RichLog)
        chat_log.clear()
        self.agent.reset_history()    # 同時清空 AI 的記憶
        chat_log.write("[dim]對話已清空。[/dim]")

    def action_new_session(self) -> None:
        """快捷鍵 Ctrl+N：開新對話（目前等同清空）"""
        self.action_clear_chat()

    def action_toggle_sidebar(self) -> None:
        """快捷鍵 F1：收合/展開左側 Sidebar"""
        sidebar = self.query_one("#sidebar")
        sidebar.display = not sidebar.display    # display=False 就是隱藏