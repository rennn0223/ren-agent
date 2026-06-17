"""
設定檔模組 — 使用 Pydantic 做型別驗證，支援 YAML 讀寫。
好處：改設定只需要改 ~/.config/ren-agent/config.yaml，不用動程式碼。
"""
from pathlib import Path          # 處理檔案路徑，跨平台不會有斜線問題
from pydantic import BaseModel, Field   # BaseModel = 有型別檢查的資料類別
import yaml                       # 讀寫 YAML 格式設定檔


class OllamaConfig(BaseModel):
    """Ollama 伺服器相關設定"""
    host: str = "http://localhost:11434"   # Ollama 預設跑在這個 port
    model: str = "qwen3.6:35b"               # 預設使用的模型名稱
    timeout: int = 120                     # 等待回應最多幾秒（大模型需要久一點）
    stream: bool = True                    # True = 打字機效果逐字輸出，False = 等全部生成完才顯示


class AgentConfig(BaseModel):
    """Agent 本身的設定"""
    name: str = "ren-agent"
    version: str = "0.1.0"
    # system_prompt = 給 AI 的角色設定，決定它的個性和能力範圍
    system_prompt: str = (
        "You are ren-agent, an intelligent automotive AI assistant. "
        "You can control the vehicle via ROS2 topics, assist with navigation, "
        "obstacle avoidance, and answer questions about the vehicle's state. "
        "Be concise, precise, and safety-conscious."
    )


class AppConfig(BaseModel):
    """整個 App 的設定，包含 Ollama 和 Agent 兩個子設定"""
    # Field(default_factory=...) = 每次建立新的 AppConfig 都會產生一個新的子物件
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "AppConfig":
        """從 YAML 檔讀取設定，如果檔案不存在就用預設值"""
        config_path = Path(path)
        if config_path.exists():
            with open(config_path) as f:
                data = yaml.safe_load(f)   # safe_load 比 load 安全，避免執行惡意 YAML
            return cls(**data)             # ** 把 dict 展開成 keyword arguments
        return cls()                       # 檔案不存在就回傳全預設值

    def save_yaml(self, path: str | Path) -> None:
        """把目前設定存成 YAML 檔（方便使用者手動編輯）"""
        config_path = Path(path)
        config_path.parent.mkdir(parents=True, exist_ok=True)  # 自動建立資料夾
        with open(config_path, "w") as f:
            yaml.dump(self.model_dump(), f, default_flow_style=False)
            # model_dump() = 把 Pydantic 物件轉成 dict
            # default_flow_style=False = 輸出多行格式，比較好讀


# 預設設定檔路徑：~/.config/ren-agent/config.yaml
DEFAULT_CONFIG_PATH = Path.home() / ".config" / "ren-agent" / "config.yaml"


def get_config() -> AppConfig:
    """取得設定，優先讀使用者的 YAML，沒有就用預設值"""
    return AppConfig.from_yaml(DEFAULT_CONFIG_PATH)
