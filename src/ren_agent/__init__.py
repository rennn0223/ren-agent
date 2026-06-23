"""
ren-agent: 車載 AI Agent（Ollama + ROS2 + Textual TUI）。

這個 __init__ 只負責把版本號從 pyproject.toml 讀出來，
讓其他模組（如 TUI welcome panel）可以 from ren_agent import __version__。
"""
from importlib.metadata import PackageNotFoundError, version

try:
    # uv build 後會把 pyproject.toml 的版本灌進 metadata
    __version__ = version("ren-agent")
except PackageNotFoundError:
    # 還沒安裝的 fallback（直接從 source 跑時）
    __version__ = "0.0.0"

__app_name__ = "ren-agent"
