"""
集中式 logging（使用 loguru）。

兩個輸出 sink：
  1. stderr — 彩色，level 由 --debug 決定
  2. logs/ren_agent.log — 永遠 DEBUG，10MB rotate、保留 7 天、舊檔壓縮

TUI 啟動時會把 stderr 接管（看不到），所以實際 debug 都靠 log file。
"""
import sys
from pathlib import Path

from loguru import logger


def setup_logger(debug: bool = False, log_file: str = "logs/ren_agent.log") -> None:
    # 清掉 loguru 預設 handler，避免重複輸出
    logger.remove()

    # ── 共用格式 ──
    level = "DEBUG" if debug else "INFO"
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan> - "
        "<level>{message}</level>"
    )

    # ── stderr sink（給 CLI 模式看）──
    logger.add(sys.stderr, format=log_format, level=level, colorize=True)

    # ── 檔案 sink（永遠 DEBUG，方便事後查）──
    Path("logs").mkdir(exist_ok=True)
    logger.add(
        log_file,
        format=log_format,
        level="DEBUG",
        rotation="10 MB",      # 超過 10MB 自動 rotate
        retention="7 days",    # 7 天前的丟掉
        compression="zip",     # 舊檔壓成 .zip
    )

    logger.info(f"Logger initialized | level={level}")
