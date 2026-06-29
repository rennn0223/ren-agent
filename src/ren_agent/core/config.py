"""
設定檔模組（Pydantic + YAML 持久化）。

設計重點：
  - 每個子設定（Ollama / Agent / Ros2）獨立 class，方便 IDE 自動補全
  - 預設值寫在 class 裡，沒有 yaml 也能跑
  - get_config() 是單例，TUI 改模型後 skill 端看到同一份
  - 設定檔位置：~/.config/ren-agent/config.yaml
"""
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


# ── Ollama 子設定 ─────────────────────────────────────
class OllamaConfig(BaseModel):
    host: str = "http://localhost:11434"
    model: str = "qwen3.6:35b"
    timeout: int = 120        # 連線逾時秒數（目前 ollama-python 沒直接用）
    stream: bool = True       # 是否串流


# ── OpenAI 子設定 ─────────────────────────────────────
class OpenAIConfig(BaseModel):
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o"


# ── Anthropic 子設定 ──────────────────────────────────
class AnthropicConfig(BaseModel):
    api_key: str = ""
    model: str = "claude-sonnet-4-6"


# ── Agent 子設定（人格 / 角色提示）────────────────────
class AgentConfig(BaseModel):
    name: str = "ren-agent"
    system_prompt: str = (
        "你是 ren-agent，一個搭載在車上的 AI 助理。"
        "你可以透過 ROS2 topics 控制車輛、協助導航、避障，並回答車輛狀態相關問題。"
        "回答務必精簡、精確、以安全為優先。"
        "請一律使用「正體中文（繁體中文）」回答，"
        "除非引用程式碼、指令、ROS topic 名稱、JSON 內容或人名，才保留原文。"
    )


# ── ROS2 子設定（topic 名稱可被使用者覆寫）─────────────
class Ros2Config(BaseModel):
    cmd_vel_topic: str = "/cmd_vel"            # /drive 發到這條（geometry_msgs/Twist）
    goal_topic: str = "/ren_agent/goal"        # /goto 發到這條（std_msgs/String + JSON）
    command_topic: str = "/ai_agent/command"   # /agent 發到這條（std_msgs/String + JSON）
    # ROS_DOMAIN_ID：None = 沿用啟動 shell 的環境變數；設值會在建立 node 前覆寫 env。
    # 透過 /domain 指令可動態切換（會重啟 rclpy context）。
    domain_id: int | None = None
    # RMW_IMPLEMENTATION：None = 沿用環境（通常是 rmw_fastrtps_cpp）。
    rmw_implementation: str | None = None


# ── 安全子設定（執行層硬限制，LLM 再怎麼幻覺也突破不了）──
class SafetyConfig(BaseModel):
    # /drive 線速度上限（m/s）；發 Twist 前一律夾限到 ±此值。
    max_linear_speed: float = 0.5
    # /drive 角速度上限（rad/s）。
    max_angular_speed: float = 1.0
    # E-stop 訊號 topic（std_msgs/Bool）；空字串 = 不額外發訊號，只送 0 速度。
    estop_topic: str = "/ren_agent/estop"
    # 單次移動的最長秒數（watchdog）：任何 /drive 一定會在此時間內自動停，
    # 不允許「無限驅動」。duration<=0 或超過上限都會被夾到此值。
    max_drive_duration: float = 5.0


# ── 頂層設定 ──────────────────────────────────────────
class AppConfig(BaseModel):
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    openai: OpenAIConfig = Field(default_factory=OpenAIConfig)
    anthropic: AnthropicConfig = Field(default_factory=AnthropicConfig)
    current_provider: str = "ollama"   # "ollama" | "openai" | "anthropic"
    agent: AgentConfig = Field(default_factory=AgentConfig)
    ros2: Ros2Config = Field(default_factory=Ros2Config)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "AppConfig":
        """讀 yaml；檔案不存在或空就用預設值。"""
        config_path = Path(path)
        if config_path.exists():
            with open(config_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return cls(**data)
        return cls()

    def save_yaml(self, path: str | Path) -> None:
        """把目前設定寫回 yaml（會建立缺少的目錄）。"""
        config_path = Path(path)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(self.model_dump(), f, sort_keys=False, allow_unicode=True)


# ── 預設路徑與單例存取 ────────────────────────────────
DEFAULT_CONFIG_PATH = Path.home() / ".config" / "ren-agent" / "config.yaml"

# 模組級單例（首次呼叫 get_config 時載入）
_cached: AppConfig | None = None


def current_model_label(config: "AppConfig") -> str:
    """Return a human-readable 'model on Provider' string for the current provider."""
    p = config.current_provider
    if p == "openai":
        return f"{config.openai.model} on OpenAI"
    if p == "anthropic":
        return f"{config.anthropic.model} on Anthropic"
    return f"{config.ollama.model} on Ollama"


def get_config() -> AppConfig:
    """
    取得目前設定的單例。
    TUI 啟動會載一次；之後 skill / drive / goto 全部共用同一份，
    所以 TUI 改 model 後 skill 看到的也是新值。
    """
    global _cached
    if _cached is None:
        _cached = AppConfig.from_yaml(DEFAULT_CONFIG_PATH)
    return _cached
