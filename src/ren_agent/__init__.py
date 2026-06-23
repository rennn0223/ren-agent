"""ren-agent: Automotive AI Agent."""
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("ren-agent")
except PackageNotFoundError:
    __version__ = "0.0.0"

__app_name__ = "ren-agent"
