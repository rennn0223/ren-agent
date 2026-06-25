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
import math

from ren_agent.core.config import get_config
from ren_agent.core.safety_state import DISARMED_MSG, is_armed
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


def _clamp(value: float, limit: float) -> float:
    """把 value 夾限在 [-limit, limit]。limit 視為非負。"""
    limit = abs(limit)
    return max(-limit, min(value, limit))


# 目前唯一的 watchdog 自動停 task。
# 持有這個參考有兩個作用：
#   1. 防止 asyncio 把 fire-and-forget task 提早 GC（官方文件警告）→ 確保自動停會發生。
#   2. 下一個移動指令 / E-stop 進來時可以取消舊的，避免舊的 stop 打斷新動作。
_auto_stop_task: "asyncio.Task | None" = None


def cancel_pending_auto_stop() -> None:
    """取消目前排程中的自動停（新指令或 E-stop 時呼叫）。"""
    global _auto_stop_task
    t = _auto_stop_task
    if t is not None and not t.done():
        t.cancel()
    _auto_stop_task = None


async def drive_skill(
    direction: str,
    speed: float = 0.3,
    duration: float = 1.0,
) -> str:
    """
    控制車子。

    direction: forward / back / left / right / stop
    speed:     線速度（m/s）或角速度（rad/s）的大小，預設 0.3（安全速度）；
               發出前會被夾限到 SafetyConfig 的上限。
    duration:  幾秒後自動 stop。<= 0 或超過 max_drive_duration 會被夾到上限
               （watchdog：不允許無限驅動，車一定會在上限內自動停）。
    """
    # ── 1. 參數驗證 ──
    direction = direction.lower().strip()
    if direction not in _DIRECTIONS:
        return f"未知方向：{direction}。可用：{', '.join(_DIRECTIONS)}"

    # ── 1.5 安全閂：未解鎖時拒絕移動（stop 永遠允許）──
    if direction != "stop" and not is_armed():
        return DISARMED_MSG

    # ── 1.6 數值衛兵：NaN/Inf 直接拒絕，避免穿過 _clamp 變成 NaN Twist 出車。
    # 負 speed 統一改成正值（方向已由 direction 表達，speed 視為 magnitude）。
    if not math.isfinite(speed):
        return f"speed 必須是有限數值，收到：{speed!r}"
    speed = abs(speed)

    # ── 2. 取 ROS2 manager ──
    ros, err = safe_get_ros2()
    if not ros:
        return f"ROS2 不可用：{err}"

    cfg = get_config()
    topic = cfg.ros2.cmd_vel_topic
    type_str = "geometry_msgs/msg/Twist"

    # ── 3. 算 linear / angular，並做執行層安全夾限 ──
    # 安全閘門：不論 speed 是使用者打的還是 LLM 給的，發出去前一律夾限到設定上限，
    # 避免「speed=99」這種失控指令真的送到車上。
    lin_dir, ang_dir = _DIRECTIONS[direction]
    raw_linear = lin_dir * speed
    raw_angular = ang_dir * speed

    safety = cfg.safety
    linear = _clamp(raw_linear, safety.max_linear_speed)
    angular = _clamp(raw_angular, safety.max_angular_speed)
    was_clamped = (linear != raw_linear) or (angular != raw_angular)

    # ── 3.5 先取消上一個排程中的自動停 ──
    # 順序很重要：必須在 publish 新 Twist 之前 cancel，否則
    # 1) 我們會 await asyncio.to_thread，讓出 event loop，
    # 2) 舊 auto_stop 的 sleep 剛好醒來，把它的「零速 publish」排進 thread pool，
    # 3) 結果新 Twist 才剛動就被舊的 stop 撞停。
    cancel_pending_auto_stop()

    # ── 4. 發第一筆 Twist ──
    # publish 是同步操作（rclpy publisher.publish 不是 async），
    # 用 to_thread 避免阻塞 TUI event loop
    try:
        await asyncio.to_thread(ros.publish, topic, type_str, _twist(linear, angular))
    except Exception as e:  # noqa: BLE001
        return f"發布 Twist 失敗：{e}"

    # 已經是 stop → 直接結束
    if direction == "stop":
        return f"已送出 stop 到 {topic}"

    # ── 4.5 watchdog：單次移動時間有硬上限，不允許無限驅動 ──
    # duration<=0（原本是「不自動停」）或超過上限，一律夾到 max_drive_duration，
    # 確保車子一定會在上限內自動停。
    max_dur = safety.max_drive_duration
    duration_capped = False
    if duration <= 0 or duration > max_dur:
        duration = max_dur
        duration_capped = True

    # ── 5. 排程 duration 秒後的自動 stop ──
    # 用 background task；參考存進 _auto_stop_task（防 GC + 可被取消）。
    global _auto_stop_task

    async def _auto_stop() -> None:
        # 被新指令 / E-stop 取消時，CancelledError 會從 sleep 拋出並讓 task
        # 進入 cancelled 狀態（不在這裡吞掉，才能正確反映取消）。
        await asyncio.sleep(duration)
        try:
            await asyncio.to_thread(ros.publish, topic, type_str, _twist(0.0, 0.0))
        except Exception:
            # 自動 stop 失敗就吞掉（已經有人下新指令的話原本就不需要再 stop）
            pass

    _auto_stop_task = asyncio.create_task(_auto_stop())
    msg = (
        f"已驅動 {direction}（linear={linear:.2f}, angular={angular:.2f}），"
        f"{duration:.1f}s 後自動 stop。"
    )
    if was_clamped:
        msg += (
            f" ⚠️ 速度已夾限至安全上限"
            f"（linear≤{safety.max_linear_speed}, angular≤{safety.max_angular_speed}）。"
        )
    if duration_capped:
        msg += f" ⚠️ 移動時間已限制為 {max_dur:.1f}s（watchdog 上限）。"
    return msg


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
                    "description": (
                        "Linear or angular magnitude. Default 0.3 (safe). "
                        "Values are hard-clamped to the configured safety limits "
                        "before being sent to the vehicle."
                    ),
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
