"""
CLI 入口 — `ren-agent tui` / `ren-agent version`。

pyproject.toml 的 [project.scripts] 把 `ren-agent` 指向這裡的 `app`。
所以 `uv run ren-agent tui` 就會跑這個檔案的 tui() 函式。
"""
import typer

from ren_agent.tui.app import RenAgentApp

# ── Typer CLI 設定 ───────────────────────────────────
# add_completion=False 關掉自動補全（保持簡單）
app = typer.Typer(
    name="ren-agent",
    help="🚗 Automotive AI Agent — TUI 車載智慧助理",
    add_completion=False,
)


@app.command()
def tui(
    # ── CLI 參數 ──
    # Option 是有預設值的選項；使用者可用 --model 覆蓋
    model: str = typer.Option(
        "qwen3.6:35b",
        "--model", "-m",
        help="要使用的 Ollama 模型名稱",
    ),
    host: str = typer.Option(
        "http://localhost:11434",
        "--host",
        help="Ollama 伺服器網址",
    ),
    debug: bool = typer.Option(
        False,
        "--debug", "-d",
        help="開啟 Debug 詳細日誌",
    ),
) -> None:
    """啟動 TUI 互動介面。"""
    # 先設好 logger 才開 TUI，否則早期 log 會跑掉
    from ren_agent.core.logger import setup_logger
    setup_logger(debug=debug)

    # 把 CLI 參數塞進 App ctor
    tui_app = RenAgentApp(model=model, ollama_host=host)
    tui_app.run()


@app.command()
def version() -> None:
    """顯示目前版本。"""
    from ren_agent import __version__
    import rich
    rich.print(f"[bold cyan]ren-agent[/bold cyan] v[yellow]{__version__}[/yellow]")


# 允許 `python -m ren_agent` 直接執行
if __name__ == "__main__":
    app()
