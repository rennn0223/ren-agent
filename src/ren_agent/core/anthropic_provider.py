"""
Anthropic provider。

使用 anthropic>=0.40 SDK。Tool calling 格式與 OpenAI 不同：
  - 工具定義用 input_schema（而非 parameters）
  - 工具呼叫結果以 role="user" + type="tool_result" 回傳
  - system prompt 是獨立參數，不放在 history 裡

純文字對話使用串流；含工具呼叫時先串流文字，最後用 get_final_message() 取工具呼叫。

安裝：pip install anthropic
"""
from __future__ import annotations

from typing import AsyncIterator

from loguru import logger

from ren_agent.core.config import AnthropicConfig
from ren_agent.core.llm_provider import BaseLLMProvider, ToolCallback

try:
    import anthropic as _sdk
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

_MAX_TOKENS = 4096


def _to_anthropic_tools(tools: list[dict]) -> list[dict]:
    """把 OpenAI-format tool 定義轉成 Anthropic format。"""
    result = []
    for t in tools:
        fn = t.get("function", {})
        result.append({
            "name": fn["name"],
            "description": fn.get("description", ""),
            "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
        })
    return result


class AnthropicProvider(BaseLLMProvider):
    def __init__(self, config: AnthropicConfig):
        if not _AVAILABLE:
            raise RuntimeError(
                "anthropic package 未安裝。請執行：pip install anthropic"
            )
        self.config = config
        self._system: str = ""
        self.history: list[dict] = []   # 只含 user / assistant 輪次
        logger.debug(f"AnthropicProvider 初始化 | model={config.model}")

    def set_system_prompt(self, prompt: str) -> None:
        self._system = prompt

    def reset_history(self) -> None:
        self.history = []

    async def chat_stream(
        self,
        user_message: str,
        tools: list[dict] | None = None,
        on_tool_call: ToolCallback | None = None,
        max_tool_iters: int = 5,
    ) -> AsyncIterator[str]:
        self.history.append({"role": "user", "content": user_message})
        client = _sdk.AsyncAnthropic(api_key=self.config.api_key)
        anthropic_tools = _to_anthropic_tools(tools) if tools else None

        for _ in range(max_tool_iters):
            full_text = ""
            tool_use_blocks: list = []

            try:
                # 串流模式：文字即時 yield；工具呼叫從 final message 取
                async with client.messages.stream(
                    model=self.config.model,
                    system=self._system,
                    messages=self.history,
                    tools=anthropic_tools or _sdk.NOT_GIVEN,
                    max_tokens=_MAX_TOKENS,
                ) as stream:
                    async for text in stream.text_stream:
                        full_text += text
                        yield text
                    final = await stream.get_final_message()
            except Exception as e:  # noqa: BLE001
                logger.error(f"Anthropic 錯誤: {e}")
                yield f"\n[錯誤] {e}"
                return

            # 收集 tool_use blocks
            for block in final.content:
                if block.type == "tool_use":
                    tool_use_blocks.append(block)

            if not tool_use_blocks:
                self.history.append({"role": "assistant", "content": full_text})
                return

            # 把這輪 assistant 回覆（含 tool_use）加進 history
            content_blocks: list[dict] = []
            if full_text:
                content_blocks.append({"type": "text", "text": full_text})
            for tu in tool_use_blocks:
                content_blocks.append({
                    "type": "tool_use",
                    "id": tu.id,
                    "name": tu.name,
                    "input": tu.input,
                })
            self.history.append({"role": "assistant", "content": content_blocks})

            # 執行工具，把結果以 role="user" + tool_result 回傳
            from ren_agent.core.skills import run_skill

            tool_results: list[dict] = []
            for tu in tool_use_blocks:
                try:
                    result = await run_skill(tu.name, **tu.input)
                except Exception as e:  # noqa: BLE001
                    result = f"[tool error] {e}"

                if on_tool_call is not None:
                    await on_tool_call(tu.name, dict(tu.input), result)

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": result,
                })

            self.history.append({"role": "user", "content": tool_results})
        else:
            yield "\n[警告] 工具呼叫超過上限，已中止。"

    async def check_connection(self) -> tuple[bool, str]:
        """用最小 request 測試 API key 是否有效。"""
        try:
            client = _sdk.AsyncAnthropic(api_key=self.config.api_key)
            await client.messages.create(
                model=self.config.model,
                max_tokens=1,
                messages=[{"role": "user", "content": "hi"}],
            )
            return True, ""
        except Exception as e:  # noqa: BLE001
            return False, str(e)
