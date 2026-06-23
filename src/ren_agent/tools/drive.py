"""drive skill — 用 geometry_msgs/Twist 控制車子。"""
from __future__ import annotations

import asyncio

from ren_agent.core.config import get_config
from ren_agent.core.skills import Skill, register_skill
from ren_agent.tools.ros2_node import safe_get_ros2

_DIRECTIONS = {
    "forward": (1.0, 0.0),
    "back":    (-1.0, 0.0),
    "left":    (0.0, 1.0),
    "right":   (0.0, -1.0),
    "stop":    (0.0, 0.0),
}


def _twist(linear: float, angular: float) -> dict:
    return {
        "linear":  {"x": linear,  "y": 0.0, "z": 0.0},
        "angular": {"x": 0.0,     "y": 0.0, "z": angular},
    }


async def drive_skill(direction: str, speed: float = 0.3, duration: float = 1.0) -> str:
    direction = direction.lower().strip()
    if direction not in _DIRECTIONS:
        return f"未知方向：{direction}。可用：{', '.join(_DIRECTIONS)}"

    ros, err = safe_get_ros2()
    if not ros:
        return f"ROS2 不可用：{err}"

    cfg = get_config()
    topic = cfg.ros2.cmd_vel_topic
    type_str = "geometry_msgs/msg/Twist"

    lin_dir, ang_dir = _DIRECTIONS[direction]
    linear = lin_dir * speed
    angular = ang_dir * speed

    try:
        await asyncio.to_thread(ros.publish, topic, type_str, _twist(linear, angular))
    except Exception as e:  # noqa: BLE001
        return f"發布 Twist 失敗：{e}"

    if direction == "stop" or duration <= 0:
        return f"已送出 stop 到 {topic}"

    async def _auto_stop() -> None:
        await asyncio.sleep(duration)
        try:
            await asyncio.to_thread(ros.publish, topic, type_str, _twist(0.0, 0.0))
        except Exception:
            pass

    asyncio.create_task(_auto_stop())
    return (
        f"已驅動 {direction}（linear={linear:.2f}, angular={angular:.2f}），"
        f"{duration:.1f}s 後自動 stop。"
    )


_DRIVE_TOOL = {
    "type": "function",
    "function": {
        "name": "drive",
        "description": (
            "Drive the vehicle. Use this when the user asks to move the car "
            "forward/backward/left/right or to stop. Auto-stops after `duration` seconds."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "enum": ["forward", "back", "left", "right", "stop"],
                },
                "speed": {
                    "type": "number",
                    "description": "Linear or angular magnitude. Default 0.3 (safe).",
                },
                "duration": {
                    "type": "number",
                    "description": "Seconds before auto-stop. Default 1.0.",
                },
            },
            "required": ["direction"],
        },
    },
}


def register_drive_skills() -> None:
    register_skill(Skill("drive", "控制車子前後左右", drive_skill, tool_schema=_DRIVE_TOOL))
