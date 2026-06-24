from __future__ import annotations

import asyncio

from ren_agent.tui.app import RenAgentApp


def test_slash_with_args_submits() -> None:
    """`/goto 機械系館` 按 Enter 應該送出（清空輸入），而不是被導去補全卡住。"""

    async def _run() -> None:
        app = RenAgentApp()
        async with app.run_test() as pilot:
            inp = app._input()
            inp.value = "/goto 機械系館"
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            # 送出後輸入框會被清空；若還卡在補全則不會清空
            assert inp.value == ""

    asyncio.run(_run())


def test_slash_name_only_completes_not_submit() -> None:
    """只打指令名稱（無空白）時，Enter 應該補全而非送出。"""

    async def _run() -> None:
        app = RenAgentApp()
        async with app.run_test() as pilot:
            inp = app._input()
            inp.value = "/hel"
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            # 補全成 "/help "（不送出，所以不會清空）
            assert inp.value.strip() == "/help"

    asyncio.run(_run())


def test_plain_message_submits() -> None:
    """一般訊息按 Enter 應該送出（清空輸入）。"""

    async def _run() -> None:
        app = RenAgentApp()
        async with app.run_test() as pilot:
            inp = app._input()
            inp.value = "你好"
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert inp.value == ""

    asyncio.run(_run())


if __name__ == "__main__":
    test_slash_with_args_submits()
    test_slash_name_only_completes_not_submit()
    test_plain_message_submits()
    print("all submit tests passed")
