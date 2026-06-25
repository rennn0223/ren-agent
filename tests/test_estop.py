from __future__ import annotations

import asyncio
from unittest.mock import patch

from ren_agent.core.config import AppConfig, SafetyConfig
from ren_agent.tools import safety


class _FakeRos:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []

    def publish(self, topic: str, type_str: str, payload: dict) -> None:
        self.calls.append((topic, type_str, payload))


def _run_estop(fake: _FakeRos, cfg: AppConfig) -> str:
    async def _run():
        with (
            patch.object(safety, "safe_get_ros2", return_value=(fake, None)),
            patch.object(safety, "get_config", return_value=cfg),
        ):
            return await safety.estop_skill()

    return asyncio.run(_run())


def test_estop_publishes_zero_twist_and_signal() -> None:
    fake = _FakeRos()
    result = _run_estop(fake, AppConfig())

    # 第一筆：cmd_vel 零速度 Twist
    topic, type_str, payload = fake.calls[0]
    assert topic == "/cmd_vel"
    assert type_str == "geometry_msgs/msg/Twist"
    assert payload["linear"]["x"] == 0.0
    assert payload["angular"]["z"] == 0.0

    # 第二筆：estop topic 訊號
    topic2, type2, payload2 = fake.calls[1]
    assert topic2 == "/ren_agent/estop"
    assert type2 == "std_msgs/msg/Bool"
    assert payload2["data"] is True

    assert "E-STOP" in result


def test_estop_without_estop_topic_only_zero_twist() -> None:
    fake = _FakeRos()
    cfg = AppConfig(safety=SafetyConfig(estop_topic=""))
    _run_estop(fake, cfg)

    assert len(fake.calls) == 1
    assert fake.calls[0][0] == "/cmd_vel"


def test_estop_ros_unavailable() -> None:
    async def _run():
        with patch.object(safety, "safe_get_ros2", return_value=(None, "no rclpy")):
            return await safety.estop_skill()

    result = asyncio.run(_run())
    assert "ROS2 不可用" in result
