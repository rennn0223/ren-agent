"""
ROS2 CLI adapter.
使用 subprocess 封裝 ros2 CLI，供 skills / services 呼叫。
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


@dataclass
class Ros2CommandResult:
    ok: bool
    stdout: str
    stderr: str = ""


class Ros2Tool:
    def __init__(self, ros2_bin: str = "ros2") -> None:
        self.ros2_bin = ros2_bin

    def is_available(self) -> bool:
        return shutil.which(self.ros2_bin) is not None

    def topic_list(self) -> Ros2CommandResult:
        if not self.is_available():
            return Ros2CommandResult(
                ok=False,
                stdout="",
                stderr="找不到 ros2 指令，請先 source ROS2 環境。",
            )

        try:
            result = subprocess.run(
                [self.ros2_bin, "topic", "list", "-t"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            return Ros2CommandResult(
                ok=result.returncode == 0,
                stdout=result.stdout.strip(),
                stderr=result.stderr.strip(),
            )
        except subprocess.TimeoutExpired:
            return Ros2CommandResult(
                ok=False,
                stdout="",
                stderr="ros2 topic list 執行逾時（5 秒）。",
            )

    def topic_echo_once(self, topic_name: str) -> Ros2CommandResult:
        if not self.is_available():
            return Ros2CommandResult(
                ok=False,
                stdout="",
                stderr="找不到 ros2 指令，請先 source ROS2 環境。",
            )

        try:
            result = subprocess.run(
                [self.ros2_bin, "topic", "echo", "--once", topic_name],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            return Ros2CommandResult(
                ok=result.returncode == 0,
                stdout=result.stdout.strip(),
                stderr=result.stderr.strip(),
            )
        except subprocess.TimeoutExpired:
            return Ros2CommandResult(
                ok=False,
                stdout="",
                stderr=f"ros2 topic echo --once {topic_name} 執行逾時（5 秒）。",
            )