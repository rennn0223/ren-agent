"""
設定檔模組 — 使用 Pydantic 做型別驗證，支援 YAML 讀寫。
好處：改設定只需要改 ~/.config/ren-agent/config.yaml，不用動程式碼。
"""
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class OllamaConfig(BaseModel):
    """Ollama 伺服器相關設定。"""

    host: str = "http://localhost:11434"
    model: str = "qwen3.6:35b"
    timeout: int = 120
    stream: bool = True


class AgentConfig(BaseModel):
    """Agent 本身的設定。"""

    name: str = "ren-agent"
    version: str = "0.3.0"
    system_prompt: str = (
        "You are ren-agent, an intelligent automotive AI assistant. "
        "You can control the vehicle via ROS2 topics, assist with navigation, "
        "obstacle avoidance, and answer questions about the vehicle's state. "
        "Be concise, precise, and safety-conscious."
    )


class AppConfig(BaseModel):
    """整個 App 的設定，包含 Ollama 和 Agent 兩個子設定。"""

    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "AppConfig":
        config_path = Path(path)
        if config_path.exists():
            with open(config_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return cls(**data)
        return cls()

    def save_yaml(self, path: str | Path) -> None:
        config_path = Path(path)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(self.model_dump(), f, sort_keys=False, allow_unicode=True)


DEFAULT_CONFIG_PATH = Path.home() / ".config" / "ren-agent" / "config.yaml"


def get_config() -> AppConfig:
    return AppConfig.from_yaml(DEFAULT_CONFIG_PATH)