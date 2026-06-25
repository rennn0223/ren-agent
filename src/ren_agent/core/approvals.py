"""
人工批准閘門（approval gate）— approval-engine 的最小雛形。

理念（對應專案規劃的「雙路徑控制 / 安全優先」）：
  - 高風險或不確定的動作（例如 LLM 觸發的「萬用發佈」ros_publish）
    不直接執行，先登記成一個「待批准動作」。
  - 使用者用 `/approve` 才真正執行、`/reject` 取消。
  - 這樣 LLM 保有強大的萬用能力，但實際送到 ROS 之前一定有人類把關。

實作上是 process 級單例：一次只保留一個待批准動作（後到覆蓋先到）。
待批准動作本體是一個「無參數 → 回字串」的 async callable，
由請求方（skill）把要做的事包成 closure 存進來。
"""
from __future__ import annotations

import contextvars
import threading
from dataclasses import dataclass
from typing import Awaitable, Callable

# 待批准動作：description 給人看，run 是實際要執行的 async 函式。
RunFunc = Callable[[], Awaitable[str]]


@dataclass
class PendingAction:
    description: str
    run: RunFunc


_lock = threading.Lock()
_pending: PendingAction | None = None

# 「目前的 async 呼叫已被人類授權」旗標。用 ContextVar 而不是 kwarg：
# - slash 指令 handler 進入時 set，呼叫 skill 時自然繼承到下游
# - LLM tool-call 路徑不會 set，LLM 也沒辦法從 tool schema 偽造這個欄位
# - 比 `_approved=True` kwarg 安全：run_skill 是 **kwargs 直送，
#   LLM 如果在 tool-call JSON 裡塞 _approved 就會被傳進去
_human_approved: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "ren_agent_human_approved", default=False
)


def is_human_approved() -> bool:
    """當前 async context 是否帶有人類授權旗標。"""
    return _human_approved.get()


def mark_human_approved() -> None:
    """
    標記「當前 async context 是人類發起的、已授權」。
    斜線指令 handler 與 `/approve` 走這條，LLM tool-call 路徑不呼叫。
    """
    _human_approved.set(True)


def request_approval(description: str, run: RunFunc) -> str:
    """
    登記一個待批准動作。若已經有待批准動作，新請求會被拒絕（避免靜默覆蓋）。
    """
    global _pending
    with _lock:
        if _pending is not None:
            return (
                f"⚠️ 已有一個待批准動作未處理（{_pending.description}）。\n"
                f"   請先 /approve 或 /reject，再送出新的動作。\n"
                f"   被拒絕的新動作：{description}"
            )
        _pending = PendingAction(description, run)
    return (
        f"⚠️ 此動作需人工批准：{description}\n"
        f"   輸入 /approve 執行，或 /reject 取消。"
    )


def has_pending() -> bool:
    """目前是否有待批准動作。"""
    return _pending is not None


def pending_description() -> str | None:
    """待批准動作的描述（沒有則 None）。一次性 snapshot，避免 TOCTOU。"""
    p = _pending
    return p.description if p is not None else None


async def approve() -> str:
    """批准並執行待批准動作；回傳執行結果。沒有待批准則回提示。"""
    global _pending
    with _lock:
        action = _pending
        _pending = None
    if action is None:
        return "目前沒有待批准的動作。"
    # 執行階段已經是「人類授權」context；下游 skill 看到 is_human_approved()=True
    mark_human_approved()
    return await action.run()


def reject() -> str:
    """取消待批准動作。"""
    global _pending
    with _lock:
        action = _pending
        _pending = None
    if action is None:
        return "目前沒有待批准的動作。"
    return f"已取消待批准動作：{action.description}"
