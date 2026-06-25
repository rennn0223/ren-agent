"""
ROS2 skills（rclpy 版）— 四個工具：

  ros_topics   列 topic 清單
  ros_echo     讀一筆訊息
  ros_type     顯示 topic 的訊息型別與欄位
  ros_publish  發布 JSON 到 topic（自動推斷型別）

實際 ROS2 邏輯都委派給 Ros2Manager（tools/ros2_node.py）。
這裡只負責：
  1. 把 sync 的 rclpy 呼叫包成 await asyncio.to_thread(...)
  2. 把 ROS2 不可用的錯誤統一格式化
  3. 提供給 LLM 看的 tool_schema
"""
from __future__ import annotations

import asyncio
import json

from ren_agent.core.config import get_config
from ren_agent.core.safety_state import DISARMED_MSG, is_armed
from ren_agent.core.skills import Skill, register_skill
from ren_agent.tools.ros2_node import (
    Ros2Manager,
    ensure_json_dict,
    reinit_ros2,
    safe_get_ros2,
)


# ── 共用 helper ──────────────────────────────────────
async def _ros_or_err() -> tuple[Ros2Manager | None, str | None]:
    """非同步取得 Ros2Manager；失敗回傳 (None, 錯誤訊息)。"""
    return await asyncio.to_thread(safe_get_ros2)


# ── 四個 skill 函式 ──────────────────────────────────
async def ros_topics_skill() -> str:
    ros, err = await _ros_or_err()
    if not ros:
        return f"ROS2 不可用：{err}"
    pairs = await asyncio.to_thread(ros.topic_names_and_types)
    if not pairs:
        return "目前沒有任何 topic。"
    lines = ["可用 ROS2 topics："]
    for name, types in sorted(pairs):
        lines.append(f"  {name}  [{', '.join(types)}]")
    return "\n".join(lines)


async def ros_echo_skill(topic: str) -> str:
    ros, err = await _ros_or_err()
    if not ros:
        return f"ROS2 不可用：{err}"
    yaml_text = await asyncio.to_thread(ros.echo_once, topic, 3.0)
    if yaml_text is None:
        return f"在 3 秒內沒收到 `{topic}` 的訊息（topic 可能不存在或沒人發布）。"
    return f"{topic}:\n{yaml_text}"


async def ros_type_skill(topic: str) -> str:
    ros, err = await _ros_or_err()
    if not ros:
        return f"ROS2 不可用：{err}"
    type_str = await asyncio.to_thread(ros.topic_type, topic)
    if not type_str:
        return f"找不到 topic `{topic}`。"
    desc = await asyncio.to_thread(ros.describe_type, type_str)
    return desc


def _clamp_twist_in_place(data: dict, max_linear: float, max_angular: float) -> bool:
    """
    對 geometry_msgs/Twist 的 payload 做安全夾限（修改 data in-place）。
    回傳是否真的有夾。
    這是執行層的最後一道防線：即使 LLM 或 ros_publish 繞過 drive_skill，
    送到 /cmd_vel 的 Twist 也不會超過 SafetyConfig 上限。
    """
    changed = False

    def _do(section: str, key: str, limit: float) -> None:
        nonlocal changed
        sub = data.get(section)
        if not isinstance(sub, dict):
            return
        v = sub.get(key)
        if not isinstance(v, (int, float)):
            return
        clamped = max(-abs(limit), min(float(v), abs(limit)))
        if clamped != v:
            sub[key] = clamped
            changed = True

    _do("linear", "x", max_linear)
    _do("linear", "y", max_linear)
    _do("angular", "z", max_angular)
    return changed


async def ros_publish_skill(
    topic: str,
    payload: str,
    type_str: str | None = None,
) -> str:
    """
    發布 JSON payload 到 topic（萬用發佈，本專案亮點）。
    若沒給 type_str，會自動從 ROS graph 推斷（要有現存 publisher/subscriber）。

    安全閘門：這是能對「任何 topic、任何型別」發任意內容的強力工具，
    會繞過 drive 的方向解析等便利機制。因此：
      1. LLM 觸發時一律需人工批准（登記成待批准動作，由使用者 /approve 才執行）
      2. 未 arm 時拒絕（同 drive/goto/route，避免靜默繞過安全閂）
      3. 對 /cmd_vel 的 Twist 仍套用 SafetyConfig 的速度夾限（最後一道防線）

    人類授權判定改用 ContextVar（is_human_approved），不再用 `_approved` kwarg；
    LLM 無法從 tool schema 看到也無法在 tool-call JSON 裡偽造。
    """
    from ren_agent.core.approvals import is_human_approved, request_approval

    if not is_human_approved():
        async def _run() -> str:
            return await ros_publish_skill(topic, payload, type_str=type_str)

        target = f"{topic}" + (f"（{type_str}）" if type_str else "")
        return request_approval(f"發布到 {target}：{payload}", _run)

    # 未 arm 一律拒絕（與 drive/goto/route/agent_command 一致；
    # 避免「approved 後就可以對 cmd_vel 任意發 Twist」的繞道）
    if not is_armed():
        return DISARMED_MSG

    ros, err = await _ros_or_err()
    if not ros:
        return f"ROS2 不可用：{err}"

    # ── 自動推斷型別 ──
    if type_str is None:
        type_str = await asyncio.to_thread(ros.topic_type, topic)
        if not type_str:
            return (
                f"找不到 topic `{topic}` 的型別。請先讓 publisher/subscriber 出現，"
                f"或用 type_str 參數指定。"
            )

    # ── parse payload ──
    try:
        data = ensure_json_dict(payload)
    except json.JSONDecodeError as e:
        return f"payload 不是合法 JSON：{e}"

    # ── Twist 夾限（最後一道防線）──
    cfg = get_config()
    clamped_note = ""
    if "Twist" in type_str and topic == cfg.ros2.cmd_vel_topic:
        safety = cfg.safety
        if _clamp_twist_in_place(data, safety.max_linear_speed, safety.max_angular_speed):
            clamped_note = (
                f" ⚠️ Twist 已夾限至安全上限"
                f"（linear≤{safety.max_linear_speed}, angular≤{safety.max_angular_speed}）。"
            )

    # ── 發布 ──
    try:
        await asyncio.to_thread(ros.publish, topic, type_str, data)
    except Exception as e:  # noqa: BLE001
        return f"發布失敗：{e}"
    return f"已發布到 {topic}（{type_str}）：{json.dumps(data, ensure_ascii=False)}{clamped_note}"


async def set_domain_skill(domain_id: int | str, rmw: str | None = None) -> str:
    """
    動態切換 ROS_DOMAIN_ID（並可選 RMW），會用新設定重啟 ROS2 node。
    """
    try:
        did = int(domain_id)
    except (TypeError, ValueError):
        return f"domain_id 必須是整數，收到：{domain_id!r}"
    if not (0 <= did <= 232):
        return f"ROS_DOMAIN_ID 應在 0–232 之間，收到 {did}"

    try:
        await asyncio.to_thread(reinit_ros2, did, rmw)
    except Exception as e:  # noqa: BLE001
        return f"切換 domain 失敗：{e}"

    extra = f"、RMW={rmw}" if rmw else ""
    return f"已切換 ROS_DOMAIN_ID={did}{extra}，ROS2 節點已用新設定重啟。"


async def agent_command_skill(cmd: str = "go_agent_route") -> str:
    """
    發一個指令給 AI agent 控制端：
    std_msgs/String，data = JSON 字串 `{"cmd": "<cmd>"}`，發到 cfg.ros2.command_topic。
    等價於同事的 `ros2 topic pub /ai_agent/command std_msgs/msg/String "data: '{...}'"`。
    """
    if not is_armed():
        return DISARMED_MSG

    cmd = (cmd or "go_agent_route").strip()
    ros, err = await _ros_or_err()
    if not ros:
        return f"ROS2 不可用：{err}"

    topic = get_config().ros2.command_topic
    payload = json.dumps({"cmd": cmd}, ensure_ascii=False)

    try:
        subs = await asyncio.to_thread(ros.publish_command, topic, payload)
    except Exception as e:  # noqa: BLE001
        return f"發布失敗：{e}"

    note = "" if subs else "（注意：目前沒有偵測到訂閱者，訊息可能沒被接收）"
    return f"已發布到 {topic}（std_msgs/String）：{payload}{note}"


# ── Tool schemas（給 LLM 看的）───────────────────────
_ROS_TOPICS_TOOL = {
    "type": "function",
    "function": {
        "name": "ros_topics",
        "description": "List all currently visible ROS2 topics with message types.",
        "parameters": {"type": "object", "properties": {}},
    },
}

_ROS_ECHO_TOOL = {
    "type": "function",
    "function": {
        "name": "ros_echo",
        "description": "Read ONE message from a ROS2 topic (3s timeout).",
        "parameters": {
            "type": "object",
            "properties": {"topic": {"type": "string"}},
            "required": ["topic"],
        },
    },
}

_ROS_TYPE_TOOL = {
    "type": "function",
    "function": {
        "name": "ros_type",
        "description": (
            "Show the message type and fields of a ROS2 topic. "
            "Call this before ros_publish if you don't know the format."
        ),
        "parameters": {
            "type": "object",
            "properties": {"topic": {"type": "string"}},
            "required": ["topic"],
        },
    },
}

_ROS_PUB_TOOL = {
    "type": "function",
    "function": {
        "name": "ros_publish",
        "description": (
            "Publish a JSON payload to a ROS2 topic. Type is auto-detected from "
            "the live graph; if unknown, call ros_type first. Payload must match "
            "the message schema as nested JSON."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "payload": {
                    "type": "string",
                    "description": 'JSON object as a string, e.g. \'{"data":"hi"}\'',
                },
            },
            "required": ["topic", "payload"],
        },
    },
}


_SET_DOMAIN_TOOL = {
    "type": "function",
    "function": {
        "name": "set_domain",
        "description": (
            "Switch the ROS_DOMAIN_ID (and optionally the RMW implementation) at "
            "runtime, restarting the ROS2 node. Use when topics are not visible "
            "because the simulator runs on a different ROS domain."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "domain_id": {
                    "type": "integer",
                    "description": "ROS_DOMAIN_ID, 0-232 (e.g. 30).",
                },
                "rmw": {
                    "type": "string",
                    "description": "Optional RMW, e.g. rmw_fastrtps_cpp.",
                },
            },
            "required": ["domain_id"],
        },
    },
}

_AGENT_CMD_TOOL = {
    "type": "function",
    "function": {
        "name": "agent_command",
        "description": (
            "Send a command to the AI agent controller via the command topic "
            "(std_msgs/String with JSON {\"cmd\": ...}). Use this to trigger "
            "routines like 'go_agent_route'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "cmd": {
                    "type": "string",
                    "description": "Command name, default 'go_agent_route'.",
                },
            },
        },
    },
}


# ── 註冊入口 ─────────────────────────────────────────
def register_ros2_skills() -> None:
    """TUI on_mount() 呼叫一次。"""
    register_skill(Skill("ros_topics", "列出 ROS2 topics", ros_topics_skill, tool_schema=_ROS_TOPICS_TOOL))
    register_skill(Skill("ros_echo", "讀取指定 topic 一次", ros_echo_skill, tool_schema=_ROS_ECHO_TOOL))
    register_skill(Skill("ros_type", "顯示 topic 的訊息型別與欄位", ros_type_skill, tool_schema=_ROS_TYPE_TOOL))
    register_skill(Skill("ros_publish", "發布 JSON 到 topic", ros_publish_skill, tool_schema=_ROS_PUB_TOOL))
    register_skill(Skill("set_domain", "切換 ROS_DOMAIN_ID（重啟節點）", set_domain_skill, tool_schema=_SET_DOMAIN_TOOL))
    register_skill(Skill("agent_command", "發指令給 AI agent 控制端", agent_command_skill, tool_schema=_AGENT_CMD_TOOL))
