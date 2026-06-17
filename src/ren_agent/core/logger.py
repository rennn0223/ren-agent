"""Centralized logging with loguru."""
import sys
from pathlib import Path
from loguru import logger


def setup_logger(debug: bool = False, log_file: str = "logs/ren_agent.log") -> None:
    logger.remove()

    level = "DEBUG" if debug else "INFO"
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan> - "
        "<level>{message}</level>"
    )

    logger.add(sys.stderr, format=log_format, level=level, colorize=True)

    Path("logs").mkdir(exist_ok=True)
    logger.add(
        log_file,
        format=log_format,
        level="DEBUG",
        rotation="10 MB",
        retention="7 days",
        compression="zip",
    )

    logger.info(f"Logger initialized | level={level}")
