"""設定檔模組（Pydantic + YAML）。"""
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class OllamaConfig(BaseModel):
    host: str = "http://localhost:11434"
    model: str = "qwen3.6:35b"
    timeout: int = 120
    stream: bool = True


class AgentConfig(BaseModel):
    name: str = "ren-agent"
    system_prompt: str = (
        "你是 ren-agent，一個搭載在車上的 AI 助理。"
        "你可以透過 ROS2 topics 控制車輛、協助導航、避障，並回答車輛狀態相關問題。"
        "回答務必精簡、精確、以安全為優先。"
        "請一律使用「正體中文（繁體中文）」回答，"
        "除非引用程式碼、指令、ROS topic 名稱、JSON 內容或人名，才保留原文。"
    )


class Ros2Config(BaseModel):
    cmd_vel_topic: str = "/cmd_vel"
    goal_topic: str = "/ren_agent/goal"  # Isaac Sim 訂閱這條 (std_msgs/String, JSON)


class AppConfig(BaseModel):
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    ros2: Ros2Config = Field(default_factory=Ros2Config)

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

_cached: AppConfig | None = None


def get_config() -> AppConfig:
    """單例設定（讓 skill 與 TUI 看到同一份）。"""
    global _cached
    if _cached is None:
        _cached = AppConfig.from_yaml(DEFAULT_CONFIG_PATH)
    return _cached
