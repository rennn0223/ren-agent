from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from ren_agent.core import approvals, safety_state
from ren_agent.tools import ros2_skills


@pytest.fixture(autouse=True)
def _clear_pending():
    approvals.reject()  # 確保每個測試從「無待批准」開始
    # ros_publish 走實際發布路徑時需要 arm；測試結束復原
    was_armed = safety_state.is_armed()
    safety_state.arm()
    yield
    approvals.reject()
    if not was_armed:
        safety_state.disarm()


class _FakeRos:
    def __init__(self) -> None:
        self.published: list[tuple] = []

    def topic_type(self, topic: str) -> str:
        return "std_msgs/msg/String"

    def publish(self, topic: str, type_str: str, data: dict) -> None:
        self.published.append((topic, type_str, data))


# ── approval gate 基本行為 ──
def test_request_then_approve_runs_and_clears() -> None:
    calls: list[int] = []

    async def _run() -> str:
        calls.append(1)
        return "done"

    msg = approvals.request_approval("做某事", _run)
    assert "需人工批准" in msg
    assert approvals.has_pending()

    result = asyncio.run(approvals.approve())
    assert result == "done"
    assert calls == [1]
    assert not approvals.has_pending()


def test_reject_discards() -> None:
    async def _run() -> str:
        return "should not run"

    approvals.request_approval("做某事", _run)
    out = approvals.reject()
    assert "已取消" in out
    assert not approvals.has_pending()


def test_approve_with_nothing_pending() -> None:
    assert "沒有待批准" in asyncio.run(approvals.approve())


# ── ros_publish 萬用發佈的人工批准閘門 ──
def test_ros_publish_via_llm_requires_approval() -> None:
    fake = _FakeRos()
    with patch.object(ros2_skills, "safe_get_ros2", return_value=(fake, None)):
        msg = asyncio.run(ros2_skills.ros_publish_skill("/chatter", '{"data":"hi"}'))

    # 沒批准前：不發布、且有待批准動作
    assert "需人工批准" in msg
    assert fake.published == []
    assert approvals.has_pending()

    # 批准後才真的發布
    with patch.object(ros2_skills, "safe_get_ros2", return_value=(fake, None)):
        result = asyncio.run(approvals.approve())
    assert "已發布" in result
    assert fake.published and fake.published[0][0] == "/chatter"
    assert not approvals.has_pending()


def test_ros_publish_manual_is_direct() -> None:
    """手打 /ros pub：在 async context 標記 human_approved 後直送，不需批准。"""
    fake = _FakeRos()

    async def _do() -> str:
        approvals.mark_human_approved()
        return await ros2_skills.ros_publish_skill("/chatter", '{"data":"hi"}')

    with patch.object(ros2_skills, "safe_get_ros2", return_value=(fake, None)):
        msg = asyncio.run(_do())
    assert "已發布" in msg
    assert fake.published
    assert not approvals.has_pending()


def test_ros_publish_blocks_second_pending() -> None:
    """已有待批准動作時，第二次 ros_publish 不會靜默覆蓋。"""
    fake = _FakeRos()
    with patch.object(ros2_skills, "safe_get_ros2", return_value=(fake, None)):
        msg1 = asyncio.run(ros2_skills.ros_publish_skill("/a", '{"data":"1"}'))
        msg2 = asyncio.run(ros2_skills.ros_publish_skill("/b", '{"data":"2"}'))
    assert "需人工批准" in msg1
    assert "已有一個待批准動作" in msg2
    assert approvals.pending_description() and "/a" in approvals.pending_description()


def test_ros_publish_disarmed_rejected_even_with_approval() -> None:
    """ros_publish 在 disarm 狀態下被拒，即使 ContextVar 已標記。"""
    fake = _FakeRos()

    async def _do() -> str:
        approvals.mark_human_approved()
        return await ros2_skills.ros_publish_skill("/chatter", '{"data":"hi"}')

    safety_state.disarm()
    try:
        with patch.object(ros2_skills, "safe_get_ros2", return_value=(fake, None)):
            msg = asyncio.run(_do())
    finally:
        safety_state.arm()
    assert "未解鎖" in msg
    assert fake.published == []


def test_ros_publish_clamps_twist_to_cmd_vel() -> None:
    """對 /cmd_vel 的 Twist 一律套 SafetyConfig 夾限（最後一道防線）。"""

    class _FakeRosTwist:
        def __init__(self) -> None:
            self.published: list[tuple] = []

        def topic_type(self, topic: str) -> str:
            return "geometry_msgs/msg/Twist"

        def publish(self, topic: str, type_str: str, data: dict) -> None:
            self.published.append((topic, type_str, data))

    fake = _FakeRosTwist()

    async def _do() -> str:
        approvals.mark_human_approved()
        return await ros2_skills.ros_publish_skill(
            "/cmd_vel",
            '{"linear":{"x":99.0,"y":0.0,"z":0.0},"angular":{"x":0.0,"y":0.0,"z":99.0}}',
        )

    with patch.object(ros2_skills, "safe_get_ros2", return_value=(fake, None)):
        msg = asyncio.run(_do())
    assert "已夾限" in msg
    assert fake.published
    pub_data = fake.published[0][2]
    # 預設 max_linear_speed=0.5, max_angular_speed=1.0
    assert pub_data["linear"]["x"] == 0.5
    assert pub_data["angular"]["z"] == 1.0


def test_ros_publish_reject_does_not_publish() -> None:
    fake = _FakeRos()
    with patch.object(ros2_skills, "safe_get_ros2", return_value=(fake, None)):
        asyncio.run(ros2_skills.ros_publish_skill("/cmd_vel", '{"data":"x"}'))
    assert approvals.has_pending()
    approvals.reject()
    assert not approvals.has_pending()
    assert fake.published == []
