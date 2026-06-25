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


def request_approval(description: str, run: RunFunc) -> str:
    """
    登記一個待批准動作，回傳給使用者看的提示字串。
    後到的請求會覆蓋先前未處理的（只保留最新一個）。
    """
    global _pending
    with _lock:
        _pending = PendingAction(description, run)
    return (
        f"⚠️ 此動作需人工批准：{description}\n"
        f"   輸入 /approve 執行，或 /reject 取消。"
    )


def has_pending() -> bool:
    """目前是否有待批准動作。"""
    return _pending is not None


def pending_description() -> str | None:
    """待批准動作的描述（沒有則 None）。"""
    return _pending.description if _pending else None


async def approve() -> str:
    """批准並執行待批准動作；回傳執行結果。沒有待批准則回提示。"""
    global _pending
    with _lock:
        action = _pending
        _pending = None
    if action is None:
        return "目前沒有待批准的動作。"
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
