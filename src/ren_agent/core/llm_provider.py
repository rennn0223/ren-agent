"""
LLM Provider 抽象層。

BaseLLMProvider 定義所有 provider（Ollama / OpenAI / Anthropic）的共同介面。
create_provider() 根據 AppConfig.current_provider 返回對應實作。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, AsyncIterator, Awaitable, Callable

if TYPE_CHECKING:
    from ren_agent.core.config import AppConfig

ToolCallback = Callable[[str, dict, str], Awaitable[None]]
"""(tool_name, arguments, result_str) — TUI 用來顯示 → 呼叫 / ← 結果。"""


class BaseLLMProvider(ABC):
    """所有 LLM provider 必須實作的介面。"""

    @abstractmethod
    def set_system_prompt(self, prompt: str) -> None: ...

    @abstractmethod
    def reset_history(self) -> None: ...

    @abstractmethod
    async def chat_stream(
        self,
        user_message: str,
        tools: list[dict] | None = None,
        on_tool_call: ToolCallback | None = None,
        max_tool_iters: int = 5,
    ) -> AsyncIterator[str]: ...

    @abstractmethod
    async def check_connection(self) -> tuple[bool, str]:
        """返回 (ok, error_message)。"""
        ...


def create_provider(config: "AppConfig") -> BaseLLMProvider:
    """根據 config.current_provider 建立並返回對應的 LLM provider。"""
    p = config.current_provider
    if p == "openai":
        from ren_agent.core.openai_provider import OpenAIProvider
        return OpenAIProvider(config.openai)
    if p == "anthropic":
        from ren_agent.core.anthropic_provider import AnthropicProvider
        return AnthropicProvider(config.anthropic)
    from ren_agent.core.ollama_client import OllamaProvider
    return OllamaProvider(config.ollama)
