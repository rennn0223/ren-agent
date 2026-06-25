"""
safety skill — 緊急停止（E-stop）。

對外：
  - estop_skill()              — async skill：立即讓車停下
  - register_safety_skills()   — 註冊到 skill registry

行為（優先級最高，越簡單越可靠）：
  1. 立即發一筆零速度 Twist 到 cmd_vel_topic（最關鍵、對任何底盤都有效）
  2. （best-effort）發 std_msgs/Bool True 到 estop_topic，給有支援的安全節點
  E-stop 不依賴 LLM；TUI 有獨立鍵盤快捷鍵直接觸發。
"""
from __future__ import annotations

import asyncio

from ren_agent.core.config import get_config
from ren_agent.core.skills import Skill, register_skill
from ren_agent.tools.ros2_node import safe_get_ros2


def _zero_twist() -> dict:
    """全零的 geometry_msgs/Twist。"""
    return {
        "linear":  {"x": 0.0, "y": 0.0, "z": 0.0},
        "angular": {"x": 0.0, "y": 0.0, "z": 0.0},
    }


async def estop_skill() -> str:
    """緊急停止：立即送 0 速度，並（若有設定）發 E-stop 訊號。"""
    ros, err = safe_get_ros2()
    if not ros:
        return f"🛑 E-STOP：ROS2 不可用（{err}），無法發送停車訊號！"

    cfg = get_config()
    notes: list[str] = []

    # 1. 立即送 0 速度（最關鍵）
    cmd_vel = cfg.ros2.cmd_vel_topic
    try:
        await asyncio.to_thread(
            ros.publish, cmd_vel, "geometry_msgs/msg/Twist", _zero_twist()
        )
        notes.append(f"已送 0 速度 → {cmd_vel}")
    except Exception as e:  # noqa: BLE001
        notes.append(f"⚠️ 送 0 速度失敗：{e}")

    # 2. best-effort 發 E-stop 訊號
    estop_topic = cfg.safety.estop_topic
    if estop_topic:
        try:
            await asyncio.to_thread(
                ros.publish, estop_topic, "std_msgs/msg/Bool", {"data": True}
            )
            notes.append(f"已發 E-stop 訊號 → {estop_topic}")
        except Exception as e:  # noqa: BLE001
            notes.append(f"⚠️ E-stop 訊號失敗：{e}")

    return "🛑 緊急停止 E-STOP：" + "；".join(notes)


def stop_now() -> bool:
    """
    同步、best-effort 送 0 速度。給「fail-safe」場景用（例如 TUI 關閉時），
    不丟例外、不依賴 event loop。回傳是否成功送出。
    """
    ros, _ = safe_get_ros2()
    if not ros:
        return False
    try:
        cfg = get_config()
        ros.publish(
            cfg.ros2.cmd_vel_topic, "geometry_msgs/msg/Twist", _zero_twist()
        )
        return True
    except Exception:  # noqa: BLE001
        return False


# ── Ollama tool schema ───────────────────────────────
_ESTOP_TOOL = {
    "type": "function",
    "function": {
        "name": "estop",
        "description": (
            "EMERGENCY STOP the vehicle immediately. Use this when the user asks to "
            "urgently stop, halt, or says things like 緊急停止 / 停下來 / 快停 / stop now."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}


def register_safety_skills() -> None:
    """TUI on_mount() 呼叫一次。"""
    register_skill(Skill("estop", "緊急停止車輛", estop_skill, tool_schema=_ESTOP_TOOL))
