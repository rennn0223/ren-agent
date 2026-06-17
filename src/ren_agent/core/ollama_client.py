"""
Ollama 非同步客戶端 — 負責跟本地 Ollama 伺服器溝通。
使用 async/await 是因為串流輸出需要「邊生成邊顯示」，
如果用同步方式會卡住整個 TUI 介面。
"""
from typing import AsyncIterator          # 標示這個函式會「一個一個」產出值（token）
from ollama import AsyncClient            # 官方 Python SDK 的非同步版本[web:83]
from loguru import logger
from ren_agent.core.config import OllamaConfig


class OllamaAgent:
    """
    封裝 Ollama 的對話功能。
    好處：之後想換模型、加工具呼叫、加 RAG，只要改這一層就好。
    """

    def __init__(self, config: OllamaConfig | None = None):
        # 如果沒傳 config 進來，就用預設值建一個新的
        self.config = config or OllamaConfig()
        # 不在這裡共用 AsyncClient，減少 event loop 相關 bug
        self.history: list[dict] = []
        logger.debug(f"OllamaAgent 初始化完成 | model={self.config.model}")

    def set_system_prompt(self, prompt: str) -> None:
        """
        設定 system prompt（AI 的角色設定）。
        system prompt 放在 history 第一筆，role 必須是 "system"。
        """
        # 先把舊的 system message 移除，避免重複
        self.history = [m for m in self.history if m.get("role") != "system"]
        # 插入到最前面（index 0），因為 system prompt 要排在所有對話之前
        self.history.insert(0, {"role": "system", "content": prompt})
        logger.debug("System prompt 已設定")

    def reset_history(self) -> None:
        """
        清空對話歷史，但保留 system prompt。
        用於「開新對話」功能，讓 AI 忘記之前說的話，但維持同樣的角色設定。
        """
        system = [m for m in self.history if m.get("role") == "system"]
        self.history = system
        logger.info("對話歷史已清空（保留 system prompt）")

    async def chat_stream(self, user_message: str) -> AsyncIterator[str]:
        """
        送出一則訊息，並以串流方式逐字 yield 回應的 token。

        官方 async 用法示意（簡化版）[web:83][web:85]：
            client = AsyncClient()
            async for part in await client.chat(..., stream=True):
                ...
        """
        # 把使用者訊息加進歷史
        self.history.append({"role": "user", "content": user_message})
        logger.debug(f"送出訊息: {user_message[:60]}...")

        full_response = ""   # 用來收集完整回應，最後存回 history

        try:
            client = AsyncClient(host=self.config.host)

            async for chunk in await client.chat(
                model=self.config.model,
                messages=self.history,
                stream=True,
            ):
                # chunk.message.content 就是這次的一小段文字（可能是一個字或幾個字）
                token = chunk.message.content or ""
                full_response += token
                yield token

            # 對話完成後，把完整回應存進歷史
            self.history.append({"role": "assistant", "content": full_response})
            logger.debug(f"回應完成，共 {len(full_response)} 字")

        except Exception as e:
            # 連線失敗時不讓程式崩潰，改成顯示錯誤訊息給使用者
            logger.error(f"Ollama 錯誤: {e}")
            yield f"\n[錯誤] 無法連線到 Ollama ({self.config.host})：{e}"

    async def check_connection(self) -> bool:
        """
        測試 Ollama 伺服器是否在線上。
        TUI 啟動時會呼叫這個，顯示在狀態列。
        回傳 True = 連線成功，False = 連線失敗。
        """
        try:
            client = AsyncClient(host=self.config.host)
            models = await client.list()
            available = [m.model for m in models.models]
            logger.info(f"Ollama 連線成功 | 可用模型: {available}")
            return True
        except Exception as e:
            logger.warning(f"Ollama 無法連線: {e}")
            return False
