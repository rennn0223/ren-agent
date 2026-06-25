from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from ren_agent.core import safety_state
from ren_agent.core.config import AppConfig
from ren_agent.tools import drive, goto, safety


@pytest.fixture(autouse=True)
def _disarmed():
    """每個測試都從「上鎖」狀態開始，並在結束時還原。"""
    safety_state.disarm()
    yield
    safety_state.disarm()


class _FakeRos:
    def __init__(self) -> None:
        self.calls: list = []

    def publish(self, *args) -> None:
        self.calls.append(args)

    def publish_command(self, *args, **kwargs) -> int:
        self.calls.append(args)
        return 1


def test_drive_blocked_when_disarmed() -> None:
    fake = _FakeRos()
    with patch.object(drive, "safe_get_ros2", return_value=(fake, None)):
        result = asyncio.run(drive.drive_skill("forward", speed=0.2, duration=0))
    assert "未解鎖" in result
    assert fake.calls == []  # 完全沒發出任何指令


def test_drive_stop_allowed_when_disarmed() -> None:
    """stop 是安全動作，未解鎖也要能執行。"""
    fake = _FakeRos()
    with patch.object(drive, "safe_get_ros2", return_value=(fake, None)):
        result = asyncio.run(drive.drive_skill("stop"))
    assert "未解鎖" not in result
    assert fake.calls  # 有送出 stop


def test_drive_allowed_after_arm() -> None:
    fake = _FakeRos()
    safety_state.arm()
    with (
        patch.object(drive, "safe_get_ros2", return_value=(fake, None)),
        patch.object(drive, "get_config", return_value=AppConfig()),
    ):
        result = asyncio.run(drive.drive_skill("forward", speed=0.2, duration=0))
    assert "未解鎖" not in result
    assert fake.calls


def test_goto_blocked_when_disarmed() -> None:
    result = asyncio.run(goto.goto_skill("應科大樓"))
    assert "未解鎖" in result


def test_estop_latches_disarm() -> None:
    """E-stop 後必須重新 arm。"""
    safety_state.arm()
    assert safety_state.is_armed() is True
    fake = _FakeRos()
    with (
        patch.object(safety, "safe_get_ros2", return_value=(fake, None)),
        patch.object(safety, "get_config", return_value=AppConfig()),
    ):
        asyncio.run(safety.estop_skill())
    assert safety_state.is_armed() is False
