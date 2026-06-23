from __future__ import annotations

import asyncio
from typing import Optional

from ren_agent.core.skills import Skill, register_skill


async def _run_ros2(*args: str, timeout: float = 5.0) -> Optional[str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            "ros2",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return None

    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        return None

    if proc.returncode != 0:
        return None
    return stdout.decode(errors="replace")


async def ros_topics_skill() -> str:
    output = await _run_ros2("topic", "list")
    if output is None:
        return "無法執行 `ros2 topic list`，請確認 ROS2 是否已安裝並載入環境。"
    return f"可用 ROS2 topics：\n{output.strip()}"


async def ros_echo_skill(topic: str) -> str:
    if not topic:
        return "請提供要讀取的 topic 名稱。"

    output = await _run_ros2("topic", "echo", topic, "--once")
    if output is None:
        return f"無法讀取 topic `{topic}`，可能不存在或 ROS2 環境未就緒。"
    return f"ROS2 topic `{topic}` 單次內容：\n{output.strip()}"


def register_ros2_skills() -> None:
    register_skill(
        Skill(
            name="ros_topics",
            description="列出目前 ROS2 topics",
            func=ros_topics_skill,
        )
    )
    register_skill(
        Skill(
            name="ros_echo",
            description="讀取指定 ROS2 topic 一次",
            func=ros_echo_skill,
        )
    )
