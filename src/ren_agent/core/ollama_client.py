"""
Ollama 非同步客戶端（含 tool calling 迴圈）。

兩個主要對外介面：
  - chat_stream(user_message, tools=...) — 主對話 + tool loop
  - check_connection() — TUI 啟動時測 Ollama 在不在

tool calling 流程：
  user 訊息 → LLM 回應（可能含 tool_calls）
    若有 tool_calls：
      1. 把 assistant 的 tool_calls 寫進 history
      2. 逐個執行 skill，把結果以 role="tool" 寫進 history
      3. 通知 TUI 顯示 → 呼叫 / ← 結果
      4. 回到 LLM 再 chat 一次（讓它看到 tool 結果再回覆）
    沒有 tool_calls：
      把 assistant 文字寫進 history，結束。

最多迭代 max_tool_iters 次，避免無窮迴圈。
"""
from __future__ import annotations

import json
from typing import Any, AsyncIterator, Awaitable, Callable

from loguru import logger
from ollama import AsyncClient

from ren_agent.core.config import OllamaConfig


# ── 型別別名 ─────────────────────────────────────────
# TUI 用這個 callback 顯示 → 呼叫 / ← 結果
ToolCallback = Callable[[str, dict, str], Awaitable[None]]
"""(tool_name, arguments, result_str) — TUI 用來顯示 → 呼叫 / ← 結果。"""


class OllamaAgent:
    """
    對外的「對話 agent」，封裝 Ollama AsyncClient + 對話 history + tool loop。
    每次切模型會建新 instance（在 TUI 的 _set_model_skill）。
    """

    def __init__(self, config: OllamaConfig | None = None):
        self.config = config or OllamaConfig()
        # history 包含 system / user / assistant / tool 訊息
        # 不在這裡持有 AsyncClient — 每次 chat 都新建一個，避免 event loop 重用的雷
        self.history: list[dict] = []
        logger.debug(f"OllamaAgent 初始化 | model={self.config.model}")

    # ── History 管理 ─────────────────────────────────
    def set_system_prompt(self, prompt: str) -> None:
        """放在 history 開頭；舊的 system 訊息會被取代。"""
        self.history = [m for m in self.history if m.get("role") != "system"]
        self.history.insert(0, {"role": "system", "content": prompt})

    def reset_history(self) -> None:
        """清空對話但保留 system prompt（給 /clear 用）。"""
        system = [m for m in self.history if m.get("role") == "system"]
        self.history = system

    # ── 主要進入點：對話 + tool loop ─────────────────────
    async def chat_stream(
        self,
        user_message: str,
        tools: list[dict] | None = None,
        on_tool_call: ToolCallback | None = None,
        max_tool_iters: int = 5,
    ) -> AsyncIterator[str]:
        """
        送出訊息並串流回覆。若提供 tools，會自動執行 tool call 迴圈。
        以 async generator 形式 yield token 出來，TUI 串流顯示。
        """
        self.history.append({"role": "user", "content": user_message})

        try:
            client = AsyncClient(host=self.config.host)
        except Exception as e:  # noqa: BLE001
            yield f"\n[錯誤] 無法建立 Ollama client：{e}"
            return

        # ── 迴圈：LLM 可能會 call 多次工具 ──
        for _ in range(max_tool_iters):
            full_text = ""           # 本輪累積的助手文字
            tool_calls: list[Any] = []  # 本輪 LLM 想呼叫的工具

            try:
                # 串流模式：一段一段 yield 文字 token
                # tools=None 時 ollama 會走純對話模式
                async for chunk in await client.chat(
                    model=self.config.model,
                    messages=self.history,
                    tools=tools or None,
                    stream=True,
                ):
                    msg = chunk.message
                    # 有 tool_calls 時通常 content 是空字串，直接收下 tool_calls
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

            # ── 沒 tool call：純對話結束 ──
            if not tool_calls:
                self.history.append({"role": "assistant", "content": full_text})
                return

            # ── 有 tool call：執行工具，把結果回灌 history，繼續迴圈 ──
            # 先把這輪 assistant 訊息（含 tool_calls）寫進 history，讓 LLM 下輪看得到
            self.history.append({
                "role": "assistant",
                "content": full_text,
                "tool_calls": [_tc_to_dict(tc) for tc in tool_calls],
            })

            # 延後 import 避免循環依賴
            from ren_agent.core.skills import run_skill

            for tc in tool_calls:
                fn_name = tc.function.name
                args = _parse_args(tc.function.arguments)
                try:
                    result = await run_skill(fn_name, **args)
                except Exception as e:  # noqa: BLE001
                    # tool 執行失敗也要回給 LLM 看，它才能改變策略
                    result = f"[tool error] {e}"

                # 通知 TUI 顯示這次呼叫（不阻塞主流程）
                if on_tool_call is not None:
                    await on_tool_call(fn_name, args, result)

                # 把工具結果以 role="tool" 加進 history（Ollama 規定）
                self.history.append({
                    "role": "tool",
                    "name": fn_name,
                    "content": result,
                })

            # 進入下一輪：LLM 看到 tool 結果後決定要繼續 call 還是回答
        else:
            # for-else：迴圈跑完沒 break = 達到上限
            yield "\n[警告] 工具呼叫超過上限，已中止。"

    # ── 連線檢查 ─────────────────────────────────────
    async def check_connection(self) -> bool:
        """TUI 啟動時叫一次。失敗會在 status bar 顯示提示。"""
        try:
            client = AsyncClient(host=self.config.host)
            await client.list()
            return True
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Ollama 無法連線: {e}")
            return False


# ── 小工具：把 Ollama tool_call 物件展平成 dict ──────────
def _parse_args(raw: Any) -> dict:
    """tc.function.arguments 可能是 dict / JSON 字串 / Pydantic 模型 — 三種都處理。"""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            return {}
    if hasattr(raw, "model_dump"):
        return raw.model_dump()
    return {}


def _tc_to_dict(tc: Any) -> dict:
    """把 ToolCall 物件轉成 dict，存進 history（讓下一輪 LLM 看得懂）。"""
    if hasattr(tc, "model_dump"):
        return tc.model_dump()
    return {
        "function": {
            "name": tc.function.name,
            "arguments": tc.function.arguments,
        }
    }
