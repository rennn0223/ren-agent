"""
drive skill — 用 geometry_msgs/Twist 控制車子前後左右。

對外：
  - drive_skill(direction, speed, duration)  — async skill
  - _DRIVE_TOOL                              — Ollama tool schema
  - register_drive_skills()                  — 註冊到 skill registry

行為：
  - 發一筆 Twist 到 cmd_vel_topic（預設 /cmd_vel）
  - 若 duration > 0 且 direction 不是 stop，會起一個背景 task
    在 duration 秒後補一筆 stop（安全考量）
"""
from __future__ import annotations

import asyncio

from ren_agent.core.config import get_config
from ren_agent.core.skills import Skill, register_skill
from ren_agent.tools.ros2_node import safe_get_ros2


# ── 方向 → (linear 係數, angular 係數)──
# linear  > 0 = 前進；< 0 = 後退
# angular > 0 = 左轉；< 0 = 右轉（ROS 慣例，右手坐標系）
_DIRECTIONS = {
    "forward": (1.0, 0.0),
    "back":    (-1.0, 0.0),
    "left":    (0.0, 1.0),
    "right":   (0.0, -1.0),
    "stop":    (0.0, 0.0),
}


def _twist(linear: float, angular: float) -> dict:
    """構造 geometry_msgs/Twist 的 dict（給 rosidl set_message_fields 用）。"""
    return {
        "linear":  {"x": linear,  "y": 0.0, "z": 0.0},
        "angular": {"x": 0.0,     "y": 0.0, "z": angular},
    }


async def drive_skill(
    direction: str,
    speed: float = 0.3,
    duration: float = 1.0,
) -> str:
    """
    控制車子。

    direction: forward / back / left / right / stop
    speed:     線速度（m/s）或角速度（rad/s）的大小，預設 0.3（安全速度）
    duration:  幾秒後自動 stop。<= 0 表示不自動 stop（停在那個速度）。
    """
    # ── 1. 參數驗證 ──
    direction = direction.lower().strip()
    if direction not in _DIRECTIONS:
        return f"未知方向：{direction}。可用：{', '.join(_DIRECTIONS)}"

    # ── 2. 取 ROS2 manager ──
    ros, err = safe_get_ros2()
    if not ros:
        return f"ROS2 不可用：{err}"

    cfg = get_config()
    topic = cfg.ros2.cmd_vel_topic
    type_str = "geometry_msgs/msg/Twist"

    # ── 3. 算 linear / angular ──
    lin_dir, ang_dir = _DIRECTIONS[direction]
    linear = lin_dir * speed
    angular = ang_dir * speed

    # ── 4. 發第一筆 Twist ──
    # publish 是同步操作（rclpy publisher.publish 不是 async），
    # 用 to_thread 避免阻塞 TUI event loop
    try:
        await asyncio.to_thread(ros.publish, topic, type_str, _twist(linear, angular))
    except Exception as e:  # noqa: BLE001
        return f"發布 Twist 失敗：{e}"

    # 已經是 stop 或不需要自動 stop → 直接結束
    if direction == "stop" or duration <= 0:
        return f"已送出 stop 到 {topic}"

    # ── 5. 排程 duration 秒後的自動 stop ──
    # 用 fire-and-forget 的 background task，呼叫端不用 await
    async def _auto_stop() -> None:
        await asyncio.sleep(duration)
        try:
            await asyncio.to_thread(ros.publish, topic, type_str, _twist(0.0, 0.0))
        except Exception:
            # 自動 stop 失敗就吞掉（已經有人下新指令的話原本就不需要再 stop）
            pass

    asyncio.create_task(_auto_stop())
    return (
        f"已驅動 {direction}（linear={linear:.2f}, angular={angular:.2f}），"
        f"{duration:.1f}s 後自動 stop。"
    )


# ── Ollama tool schema（LLM 看到的描述）──────────────
# description 寫得越清楚，LLM 越知道何時該呼叫
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
    """TUI on_mount() 呼叫一次。"""
    register_skill(Skill("drive", "控制車子前後左右", drive_skill, tool_schema=_DRIVE_TOOL))
