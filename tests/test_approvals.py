from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from ren_agent.core import approvals
from ren_agent.tools import ros2_skills


@pytest.fixture(autouse=True)
def _clear_pending():
    approvals.reject()  # 確保每個測試從「無待批准」開始
    yield
    approvals.reject()


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
    """手打 /ros pub（_approved=True）直送，不需批准。"""
    fake = _FakeRos()
    with patch.object(ros2_skills, "safe_get_ros2", return_value=(fake, None)):
        msg = asyncio.run(
            ros2_skills.ros_publish_skill("/chatter", '{"data":"hi"}', _approved=True)
        )
    assert "已發布" in msg
    assert fake.published
    assert not approvals.has_pending()


def test_ros_publish_reject_does_not_publish() -> None:
    fake = _FakeRos()
    with patch.object(ros2_skills, "safe_get_ros2", return_value=(fake, None)):
        asyncio.run(ros2_skills.ros_publish_skill("/cmd_vel", '{"data":"x"}'))
    assert approvals.has_pending()
    approvals.reject()
    assert not approvals.has_pending()
    assert fake.published == []
