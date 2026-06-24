"""
Context / token 估算工具。

沒有真正的 tokenizer，這裡用「字元數 / 4」的啟發式來粗估 token 數，
足夠用來在狀態列顯示 context 用量與 thinking 動畫的 token 計數。
"""
from __future__ import annotations

from typing import Iterable, Mapping

# 平均每個 token 約 4 個字元（英文）；中文會略為低估，但作為提示足夠。
_CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """粗估一段文字的 token 數。"""
    if not text:
        return 0
    return max(1, len(text) // _CHARS_PER_TOKEN)


def history_token_usage(history: Iterable[Mapping[str, str]]) -> int:
    """加總對話歷史（含 system/user/assistant）的估計 token 數。"""
    return sum(estimate_tokens(str(m.get("content", ""))) for m in history)


def format_token_count(n: int) -> str:
    """把 token 數格式化成易讀字串，例如 1234 -> 1.2k。"""
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)
