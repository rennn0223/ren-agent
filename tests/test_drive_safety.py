from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from ren_agent.core import safety_state
from ren_agent.core.config import AppConfig
from ren_agent.tools import drive


@pytest.fixture(autouse=True)
def _armed():
    """這些測試都在「已解鎖」前提下驗證夾限/watchdog 行為。"""
    safety_state.arm()
    yield
    safety_state.disarm()


class _FakeRos:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []

    def publish(self, topic: str, type_str: str, payload: dict) -> None:
        self.calls.append((topic, type_str, payload))


def _cfg() -> AppConfig:
    # 預設 max_linear=0.5, max_angular=1.0
    return AppConfig()


def _run_drive(fake: _FakeRos, **kwargs):
    async def _run():
        with (
            patch.object(drive, "safe_get_ros2", return_value=(fake, None)),
            patch.object(drive, "get_config", return_value=_cfg()),
        ):
            return await drive.drive_skill(**kwargs)

    return asyncio.run(_run())


def test_drive_clamps_excessive_linear() -> None:
    fake = _FakeRos()
    _run_drive(fake, direction="forward", speed=99.0, duration=0)
    # 發出去的 Twist linear 必須被夾到 0.5，而不是 99
    assert fake.calls[0][2]["linear"]["x"] == 0.5


def test_drive_clamps_excessive_angular() -> None:
    fake = _FakeRos()
    _run_drive(fake, direction="left", speed=99.0, duration=0)
    assert fake.calls[0][2]["angular"]["z"] == 1.0


def test_drive_clamps_negative_direction() -> None:
    fake = _FakeRos()
    _run_drive(fake, direction="back", speed=99.0, duration=0)
    # back = 負方向，夾到 -0.5
    assert fake.calls[0][2]["linear"]["x"] == -0.5


def test_drive_within_limit_not_clamped() -> None:
    fake = _FakeRos()
    result = _run_drive(fake, direction="forward", speed=0.2, duration=0)
    assert fake.calls[0][2]["linear"]["x"] == 0.2
    assert "夾限" not in result


def _cfg_short_watchdog() -> AppConfig:
    cfg = AppConfig()
    cfg.safety.max_drive_duration = 0.05
    return cfg


def test_drive_caps_infinite_duration() -> None:
    """duration<=0 不再是無限驅動，會被夾到 watchdog 上限並自動停。"""
    fake = _FakeRos()

    async def _run():
        with (
            patch.object(drive, "safe_get_ros2", return_value=(fake, None)),
            patch.object(drive, "get_config", return_value=_cfg_short_watchdog()),
        ):
            result = await drive.drive_skill("forward", speed=0.2, duration=0)
            await asyncio.sleep(0.15)  # 等 watchdog 自動 stop
            return result

    result = asyncio.run(_run())
    assert "watchdog" in result
    # 最後一筆一定是 stop（0 速度）
    assert fake.calls[-1][2]["linear"]["x"] == 0.0


def test_drive_caps_excessive_duration() -> None:
    fake = _FakeRos()

    async def _run():
        with (
            patch.object(drive, "safe_get_ros2", return_value=(fake, None)),
            patch.object(drive, "get_config", return_value=_cfg_short_watchdog()),
        ):
            result = await drive.drive_skill("forward", speed=0.2, duration=999)
            await asyncio.sleep(0.15)
            return result

    result = asyncio.run(_run())
    assert "watchdog" in result
    assert fake.calls[-1][2]["linear"]["x"] == 0.0


def test_new_drive_cancels_previous_auto_stop() -> None:
    """連續兩個移動指令：前一個的 auto-stop 應被取消，不會打斷新動作。"""
    fake = _FakeRos()

    async def _run():
        with (
            patch.object(drive, "safe_get_ros2", return_value=(fake, None)),
            patch.object(drive, "get_config", return_value=AppConfig()),
        ):
            await drive.drive_skill("forward", speed=0.2, duration=5)
            first = drive._auto_stop_task
            await drive.drive_skill("forward", speed=0.2, duration=5)
            second = drive._auto_stop_task
            drive.cancel_pending_auto_stop()  # 收尾，避免遺留 pending task
            await asyncio.sleep(0)            # 讓取消生效
            return first, second

    first, second = asyncio.run(_run())
    assert first is not second
    assert first.cancelled()
    assert second.cancelled()


def test_drive_reports_clamp_warning_and_auto_stops() -> None:
    fake = _FakeRos()

    async def _run():
        with (
            patch.object(drive, "safe_get_ros2", return_value=(fake, None)),
            patch.object(drive, "get_config", return_value=_cfg()),
        ):
            result = await drive.drive_skill("forward", speed=99.0, duration=0.05)
            await asyncio.sleep(0.15)  # 等 auto_stop 背景任務跑完
            return result

    result = asyncio.run(_run())
    assert "夾限" in result
    # 第一筆是夾限後的速度，最後一筆是 auto stop
    assert fake.calls[0][2]["linear"]["x"] == 0.5
    assert fake.calls[-1][2]["linear"]["x"] == 0.0
