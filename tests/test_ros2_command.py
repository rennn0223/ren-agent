from __future__ import annotations

import asyncio
from unittest.mock import patch

from ren_agent.tools import ros2_skills


class _FakeRos:
    def __init__(self, subs: int = 1) -> None:
        self.calls: list[tuple[str, str]] = []
        self._subs = subs

    def publish_command(self, topic: str, payload: str, wait_timeout: float = 2.0) -> int:
        self.calls.append((topic, payload))
        return self._subs


def test_agent_command_publishes_std_string_json() -> None:
    fake = _FakeRos(subs=1)
    with patch.object(ros2_skills, "safe_get_ros2", return_value=(fake, None)):
        result = asyncio.run(ros2_skills.agent_command_skill("go_agent_route"))

    assert fake.calls, "應該有發布一次"
    topic, payload = fake.calls[0]
    assert topic == "/ai_agent/command"
    assert '"cmd": "go_agent_route"' in payload
    assert "已發布" in result
    assert "沒有偵測到訂閱者" not in result


def test_agent_command_warns_when_no_subscriber() -> None:
    fake = _FakeRos(subs=0)
    with patch.object(ros2_skills, "safe_get_ros2", return_value=(fake, None)):
        result = asyncio.run(ros2_skills.agent_command_skill())  # 預設 go_agent_route

    assert "沒有偵測到訂閱者" in result


def test_agent_command_ros_unavailable() -> None:
    with patch.object(ros2_skills, "safe_get_ros2", return_value=(None, "no rclpy")):
        result = asyncio.run(ros2_skills.agent_command_skill("go_agent_route"))
    assert "ROS2 不可用" in result


def test_set_domain_rejects_non_integer() -> None:
    result = asyncio.run(ros2_skills.set_domain_skill("abc"))
    assert "必須是整數" in result


def test_set_domain_rejects_out_of_range() -> None:
    result = asyncio.run(ros2_skills.set_domain_skill(999))
    assert "0" in result and "232" in result


def test_set_domain_calls_reinit() -> None:
    called: dict[str, object] = {}

    def fake_reinit(domain_id=None, rmw=None):
        called["domain_id"] = domain_id
        called["rmw"] = rmw
        return object()

    with patch.object(ros2_skills, "reinit_ros2", fake_reinit):
        result = asyncio.run(ros2_skills.set_domain_skill(30, "rmw_fastrtps_cpp"))

    assert called == {"domain_id": 30, "rmw": "rmw_fastrtps_cpp"}
    assert "30" in result
