"""
OpenAI / OpenAI-compatible provider。

使用 openai>=1.0 SDK。Tool calling 格式與 Ollama 相同（都是 OpenAI 標準），
所以現有的 skill tool 定義可以直接傳入，不需轉換。

安裝：pip install openai
"""
from __future__ import annotations

import json
from typing import Any, AsyncIterator

from loguru import logger

from ren_agent.core.config import OpenAIConfig
from ren_agent.core.llm_provider import BaseLLMProvider, ToolCallback

try:
    from openai import AsyncOpenAI
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False


class OpenAIProvider(BaseLLMProvider):
    def __init__(self, config: OpenAIConfig):
        if not _AVAILABLE:
            raise RuntimeError(
                "openai package 未安裝。請執行：pip install openai"
            )
        self.config = config
        self.history: list[dict] = []
        logger.debug(f"OpenAIProvider 初始化 | model={config.model}")

    def set_system_prompt(self, prompt: str) -> None:
        self.history = [m for m in self.history if m.get("role") != "system"]
        self.history.insert(0, {"role": "system", "content": prompt})

    def reset_history(self) -> None:
        system = [m for m in self.history if m.get("role") == "system"]
        self.history = system

    async def chat_stream(
        self,
        user_message: str,
        tools: list[dict] | None = None,
        on_tool_call: ToolCallback | None = None,
        max_tool_iters: int = 5,
    ) -> AsyncIterator[str]:
        self.history.append({"role": "user", "content": user_message})
        client = AsyncOpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
        )

        for _ in range(max_tool_iters):
            full_text = ""
            # 用 dict 而非 ToolCall 物件，方便 JSON 序列化
            tc_acc: dict[int, dict] = {}

            try:
                stream = await client.chat.completions.create(
                    model=self.config.model,
                    messages=self.history,
                    tools=tools or None,
                    stream=True,
                )
                async for chunk in stream:
                    choice = chunk.choices[0] if chunk.choices else None
                    if choice is None:
                        continue
                    delta = choice.delta
                    if delta.content:
                        full_text += delta.content
                        yield delta.content
                    if delta.tool_calls:
                        for tc in delta.tool_calls:
                            idx = tc.index
                            if idx not in tc_acc:
                                tc_acc[idx] = {
                                    "id": tc.id or "",
                                    "type": "function",
                                    "function": {
                                        "name": tc.function.name or "",
                                        "arguments": "",
                                    },
                                }
                            fn = tc_acc[idx]["function"]
                            if tc.function.name:
                                fn["name"] = tc.function.name
                            if tc.function.arguments:
                                fn["arguments"] += tc.function.arguments
                            if tc.id:
                                tc_acc[idx]["id"] = tc.id
            except Exception as e:  # noqa: BLE001
                logger.error(f"OpenAI 錯誤: {e}")
                yield f"\n[錯誤] {e}"
                return

            tool_calls = list(tc_acc.values())

            if not tool_calls:
                self.history.append({"role": "assistant", "content": full_text})
                return

            self.history.append({
                "role": "assistant",
                "content": full_text or None,
                "tool_calls": tool_calls,
            })

            from ren_agent.core.skills import run_skill

            for tc in tool_calls:
                fn_name = tc["function"]["name"]
                raw_args = tc["function"]["arguments"]
                args: dict[str, Any] = {}
                if raw_args:
                    try:
                        args = json.loads(raw_args)
                    except json.JSONDecodeError:
                        args = {}

                try:
                    result = await run_skill(fn_name, **args)
                except Exception as e:  # noqa: BLE001
                    result = f"[tool error] {e}"

                if on_tool_call is not None:
                    await on_tool_call(fn_name, args, result)

                self.history.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": result,
                })
        else:
            yield "\n[警告] 工具呼叫超過上限，已中止。"

    async def check_connection(self) -> tuple[bool, str]:
        """測試 API key + endpoint 是否可用。"""
        try:
            client = AsyncOpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
            )
            await client.models.list()
            return True, ""
        except Exception as e:  # noqa: BLE001
            return False, str(e)
