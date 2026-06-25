from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from ren_agent.core import safety_state
from ren_agent.tools import goto


@pytest.fixture(autouse=True)
def _armed():
    safety_state.arm()
    yield
    safety_state.disarm()


class _FakeRos:
    def __init__(self, subs: int = 1) -> None:
        self.calls: list[tuple[str, str]] = []
        self._subs = subs

    def publish_command(self, topic: str, payload: str, wait_timeout: float = 2.0) -> int:
        self.calls.append((topic, payload))
        return self._subs


_LOCS = {
    "應科大樓": {"x": 1.0, "y": 2.0},
    "機械系館": {"x": 3.0, "y": 4.0},
}


def test_resolve_location_substring() -> None:
    assert goto._resolve_location("應科", _LOCS) == "應科大樓"
    assert goto._resolve_location("機械系館", _LOCS) == "機械系館"
    assert goto._resolve_location("不存在", _LOCS) is None


def test_route_publishes_and_reports_both_coords() -> None:
    fake = _FakeRos(subs=1)
    with (
        patch.object(goto, "_load_locations", return_value=_LOCS),
        patch.object(goto, "safe_get_ros2", return_value=(fake, None)),
    ):
        result = asyncio.run(goto.route_skill("應科", "機械系館"))

    assert fake.calls, "應該發布一次 go_agent_route"
    _, payload = fake.calls[0]
    assert '"cmd": "go_agent_route"' in payload
    assert "應科大樓: x=1.0, y=2.0" in result
    assert "機械系館: x=3.0, y=4.0" in result
    assert "已發布 go_agent_route" in result


def test_route_reports_coords_even_without_ros() -> None:
    with (
        patch.object(goto, "_load_locations", return_value=_LOCS),
        patch.object(goto, "safe_get_ros2", return_value=(None, "no rclpy")),
    ):
        result = asyncio.run(goto.route_skill("應科", "機械系館"))

    assert "應科大樓: x=1.0, y=2.0" in result
    assert "機械系館: x=3.0, y=4.0" in result
    assert "未發布 go_agent_route" in result


def test_route_missing_location() -> None:
    with patch.object(goto, "_load_locations", return_value=_LOCS):
        result = asyncio.run(goto.route_skill("應科", "外太空"))
    assert "找不到地點" in result
    assert "外太空" in result
