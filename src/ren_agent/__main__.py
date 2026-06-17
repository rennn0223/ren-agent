"""
CLI 入口點 — 使用 Typer 處理命令列參數。
pyproject.toml 裡的 [project.scripts] 把 `ren-agent` 指令指向這裡的 app。
所以執行 `uv run ren-agent tui` 就等於執行這個檔案的 tui() 函式。
"""
import typer
from ren_agent.tui.app import RenAgentApp

# 建立 Typer CLI 應用程式
# add_completion=False = 不要自動補全功能（保持簡單）
app = typer.Typer(
    name="ren-agent",
    help="🚗 Automotive AI Agent — TUI 車載智慧助理",
    add_completion=False,
)


@app.command()
def tui(
    # Option = 有預設值的選項，使用者可以用 --model 覆蓋
    model: str = typer.Option(
        "qwen3.6:35b",
        "--model", "-m",
        help="要使用的 Ollama 模型名稱"
    ),
    host: str = typer.Option(
        "http://localhost:11434",
        "--host",
        help="Ollama 伺服器網址"
    ),
    debug: bool = typer.Option(
        False,
        "--debug", "-d",
        help="開啟 Debug 詳細日誌"
    ),
):
    """啟動 TUI 互動介面"""
    from ren_agent.core.logger import setup_logger
    setup_logger(debug=debug)    # 先設定好日誌系統

    # 建立 TUI App 實例並啟動，把 CLI 參數傳進去
    tui_app = RenAgentApp(model=model, ollama_host=host)
    tui_app.run()


@app.command()
def version():
    """顯示目前版本"""
    from ren_agent import __version__
    import rich
    rich.print(f"[bold cyan]ren-agent[/bold cyan] v[yellow]{__version__}[/yellow]")


# 讓這個檔案也可以用 `python -m ren_agent` 直接執行
if __name__ == "__main__":
    app()
