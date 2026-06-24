from __future__ import annotations

from ren_agent.core.context import (
    estimate_tokens,
    format_token_count,
    history_token_usage,
)


def test_estimate_tokens_empty_is_zero() -> None:
    assert estimate_tokens("") == 0


def test_estimate_tokens_uses_char_heuristic() -> None:
    # 8 字元 / 4 = 2
    assert estimate_tokens("abcdefgh") == 2
    # 不足一個 token 也至少算 1
    assert estimate_tokens("ab") == 1


def test_history_token_usage_sums_contents() -> None:
    history = [
        {"role": "system", "content": "abcd"},      # 1
        {"role": "user", "content": "abcdefgh"},     # 2
        {"role": "assistant", "content": ""},        # 0
    ]
    assert history_token_usage(history) == 3


def test_history_token_usage_handles_missing_content() -> None:
    history = [{"role": "user"}]
    assert history_token_usage(history) == 0


def test_format_token_count() -> None:
    assert format_token_count(0) == "0"
    assert format_token_count(999) == "999"
    assert format_token_count(1000) == "1.0k"
    assert format_token_count(1234) == "1.2k"
