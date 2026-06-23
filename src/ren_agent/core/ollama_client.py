"""Ollama 非同步客戶端（含 tool calling 迴圈）。"""
from __future__ import annotations

import json
from typing import Any, AsyncIterator, Awaitable, Callable

from loguru import logger
from ollama import AsyncClient

from ren_agent.core.config import OllamaConfig


ToolCallback = Callable[[str, dict, str], Awaitable[None]]
"""(tool_name, arguments, result_str) — TUI 用來顯示 → 呼叫 / ← 結果"""


class OllamaAgent:
    def __init__(self, config: OllamaConfig | None = None):
        self.config = config or OllamaConfig()
        self.history: list[dict] = []
        logger.debug(f"OllamaAgent 初始化 | model={self.config.model}")

    def set_system_prompt(self, prompt: str) -> None:
        self.history = [m for m in self.history if m.get("role") != "system"]
        self.history.insert(0, {"role": "system", "content": prompt})

    def reset_history(self) -> None:
        system = [m for m in self.history if m.get("role") == "system"]
        self.history = system

    # ── 主要進入點 ────────────────────────────────────────

    async def chat_stream(
        self,
        user_message: str,
        tools: list[dict] | None = None,
        on_tool_call: ToolCallback | None = None,
        max_tool_iters: int = 5,
    ) -> AsyncIterator[str]:
        """送出訊息並串流回覆。若提供 tools，會自動執行 tool call 迴圈。"""
        self.history.append({"role": "user", "content": user_message})

        try:
            client = AsyncClient(host=self.config.host)
        except Exception as e:  # noqa: BLE001
            yield f"\n[錯誤] 無法建立 Ollama client：{e}"
            return

        for _ in range(max_tool_iters):
            full_text = ""
            tool_calls: list[Any] = []

            try:
                async for chunk in await client.chat(
                    model=self.config.model,
                    messages=self.history,
                    tools=tools or None,
                    stream=True,
                ):
                    msg = chunk.message
                    if msg.tool_calls:
                        tool_calls = list(msg.tool_calls)
                    token = msg.content or ""
                    if token:
                        full_text += token
                        yield token
            except Exception as e:  # noqa: BLE001
                logger.error(f"Ollama 錯誤: {e}")
                yield f"\n[錯誤] {e}"
                return

            if not tool_calls:
                self.history.append({"role": "assistant", "content": full_text})
                return

            # 紀錄 assistant 的 tool_calls 訊息
            self.history.append({
                "role": "assistant",
                "content": full_text,
                "tool_calls": [_tc_to_dict(tc) for tc in tool_calls],
            })

            # 執行每個 tool
            from ren_agent.core.skills import run_skill  # 避免循環 import

            for tc in tool_calls:
                fn_name = tc.function.name
                args = _parse_args(tc.function.arguments)
                try:
                    result = await run_skill(fn_name, **args)
                except Exception as e:  # noqa: BLE001
                    result = f"[tool error] {e}"
                if on_tool_call is not None:
                    await on_tool_call(fn_name, args, result)
                self.history.append({
                    "role": "tool",
                    "name": fn_name,
                    "content": result,
                })

            # 迴圈：再丟回 LLM，看是否還要再 call 或開始回答
        else:
            yield "\n[警告] 工具呼叫超過上限，已中止。"

    async def check_connection(self) -> bool:
        try:
            client = AsyncClient(host=self.config.host)
            await client.list()
            return True
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Ollama 無法連線: {e}")
            return False


def _parse_args(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            return {}
    # Pydantic model
    if hasattr(raw, "model_dump"):
        return raw.model_dump()
    return {}


def _tc_to_dict(tc: Any) -> dict:
    if hasattr(tc, "model_dump"):
        return tc.model_dump()
    return {
        "function": {
            "name": tc.function.name,
            "arguments": tc.function.arguments,
        }
    }
