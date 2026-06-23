"""
goto skill — 把地點轉成 {x, y} JSON 發給 Isaac Sim。

對外：
  - goto_skill(name)        — 送出指定地點座標
  - goto_list_skill()       — 列出所有可用地點
  - _GOTO_TOOL / _GOTO_LIST_TOOL — Ollama tool schema
  - register_goto_skills()  — 註冊

資料來源：
  src/ren_agent/data/locations.yaml
    locations:
      應科大樓: { x: ..., y: ... }
      機械系館: { x: ..., y: ... }

訊息格式：
  std_msgs/String，data 欄位填 JSON 字串 `{"x": ..., "y": ...}`
  發到 cfg.ros2.goal_topic（預設 /ren_agent/goal）

要換成 geometry_msgs/PointStamped 或別的格式，改 publish_json_string 為
直接呼叫 ros.publish(topic, "geometry_msgs/msg/...", {...}) 即可。
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Dict

import yaml

from ren_agent.core.config import get_config
from ren_agent.core.skills import Skill, register_skill
from ren_agent.tools.ros2_node import safe_get_ros2


# 預設座標表位置（會跟著 package 安裝）
_DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "locations.yaml"


def _load_locations() -> Dict[str, Dict[str, float]]:
    """每次呼叫都重讀，方便使用者改 yaml 立刻生效，不用重啟 TUI。"""
    with open(_DATA_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("locations", {})


async def goto_skill(name: str) -> str:
    """送出指定地點 → JSON {x, y} → Isaac Sim。"""
    name = name.strip()
    locations = _load_locations()
    if name not in locations:
        choices = "、".join(locations) or "（無）"
        return f"沒有「{name}」這個地點。可用：{choices}"

    coord = locations[name]
    # ensure_ascii=False 才能保留中文（雖然這支 payload 只有數字）
    payload = json.dumps({"x": coord["x"], "y": coord["y"]}, ensure_ascii=False)

    ros, err = safe_get_ros2()
    if not ros:
        return f"ROS2 不可用：{err}"

    cfg = get_config()
    topic = cfg.ros2.goal_topic

    try:
        await asyncio.to_thread(ros.publish_json_string, topic, payload)
    except Exception as e:  # noqa: BLE001
        return f"發布座標失敗：{e}"
    return f"已送出 {name} → {topic}: {payload}"


async def goto_list_skill() -> str:
    """印出所有已知地點與座標。"""
    locations = _load_locations()
    if not locations:
        return "locations.yaml 是空的。"
    lines = ["可用地點："]
    for name, coord in locations.items():
        lines.append(f"  {name}  x={coord['x']}, y={coord['y']}")
    return "\n".join(lines)


# ── Ollama tool schema ───────────────────────────────
_GOTO_TOOL = {
    "type": "function",
    "function": {
        "name": "goto",
        "description": (
            "Send a named campus location (e.g., 應科大樓, 機械系館) as JSON {x,y} "
            "to Isaac Sim. Use this when the user asks to navigate to / go to a place."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Location name (must match locations.yaml).",
                },
            },
            "required": ["name"],
        },
    },
}

_GOTO_LIST_TOOL = {
    "type": "function",
    "function": {
        "name": "goto_list",
        "description": "List all known locations available to `goto`.",
        "parameters": {"type": "object", "properties": {}},
    },
}


def register_goto_skills() -> None:
    """TUI on_mount() 呼叫一次。"""
    register_skill(Skill("goto", "送出地點座標給 Isaac Sim", goto_skill, tool_schema=_GOTO_TOOL))
    register_skill(Skill("goto_list", "列出可用地點", goto_list_skill, tool_schema=_GOTO_LIST_TOOL))
