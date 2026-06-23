from __future__ import annotations

import subprocess
from unittest.mock import Mock, patch

from ren_agent.tools.ros2_cli import Ros2Tool


def test_is_available_true() -> None:
    tool = Ros2Tool()

    with patch("ren_agent.tools.ros2_cli.shutil.which", return_value="/usr/bin/ros2"):
        assert tool.is_available() is True


def test_topic_list_success() -> None:
    tool = Ros2Tool()

    completed = Mock()
    completed.returncode = 0
    completed.stdout = "/cmd_vel [geometry_msgs/msg/Twist]\n/odom [nav_msgs/msg/Odometry]\n"
    completed.stderr = ""

    with patch("ren_agent.tools.ros2_cli.shutil.which", return_value="/usr/bin/ros2"):
        with patch("ren_agent.tools.ros2_cli.subprocess.run", return_value=completed):
            result = tool.topic_list()

    assert result.ok is True
    assert "/cmd_vel" in result.stdout
    assert result.stderr == ""


def test_topic_echo_once_ros2_not_found() -> None:
    tool = Ros2Tool()

    with patch("ren_agent.tools.ros2_cli.shutil.which", return_value=None):
        result = tool.topic_echo_once("/odom")

    assert result.ok is False
    assert result.stdout == ""
    assert "找不到 ros2 指令" in result.stderr


def test_topic_list_timeout() -> None:
    tool = Ros2Tool()

    with patch("ren_agent.tools.ros2_cli.shutil.which", return_value="/usr/bin/ros2"):
        with patch(
            "ren_agent.tools.ros2_cli.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["ros2"], timeout=5),
        ):
            result = tool.topic_list()

    assert result.ok is False
    assert result.stdout == ""
    assert "執行逾時" in result.stderr