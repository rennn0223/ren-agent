"""ROS2 skills（rclpy 版本）。"""
from __future__ import annotations

import asyncio
import json

from ren_agent.core.skills import Skill, register_skill
from ren_agent.tools.ros2_node import Ros2Manager, ensure_json_dict, safe_get_ros2


async def _ros_or_err() -> tuple[Ros2Manager | None, str | None]:
    return await asyncio.to_thread(safe_get_ros2)


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


async def ros_publish_skill(topic: str, payload: str, type_str: str | None = None) -> str:
    ros, err = await _ros_or_err()
    if not ros:
        return f"ROS2 不可用：{err}"

    if type_str is None:
        type_str = await asyncio.to_thread(ros.topic_type, topic)
        if not type_str:
            return (
                f"找不到 topic `{topic}` 的型別。請先讓 publisher/subscriber 出現，"
                f"或用 type_str 參數指定。"
            )

    try:
        data = ensure_json_dict(payload)
    except json.JSONDecodeError as e:
        return f"payload 不是合法 JSON：{e}"

    try:
        await asyncio.to_thread(ros.publish, topic, type_str, data)
    except Exception as e:  # noqa: BLE001
        return f"發布失敗：{e}"
    return f"已發布到 {topic}（{type_str}）：{json.dumps(data, ensure_ascii=False)}"


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
        "description": "Show the message type and fields of a ROS2 topic. "
                       "Call this before ros_publish if you don't know the format.",
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


def register_ros2_skills() -> None:
    register_skill(Skill("ros_topics", "列出 ROS2 topics", ros_topics_skill, tool_schema=_ROS_TOPICS_TOOL))
    register_skill(Skill("ros_echo", "讀取指定 topic 一次", ros_echo_skill, tool_schema=_ROS_ECHO_TOOL))
    register_skill(Skill("ros_type", "顯示 topic 的訊息型別與欄位", ros_type_skill, tool_schema=_ROS_TYPE_TOOL))
    register_skill(Skill("ros_publish", "發布 JSON 到 topic", ros_publish_skill, tool_schema=_ROS_PUB_TOOL))
