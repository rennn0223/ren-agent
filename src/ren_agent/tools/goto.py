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
from ren_agent.core.safety_state import DISARMED_MSG, is_armed
from ren_agent.core.skills import Skill, register_skill
from ren_agent.tools.ros2_node import safe_get_ros2


# 預設座標表位置（會跟著 package 安裝）
_DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "locations.yaml"


def _load_locations() -> Dict[str, Dict[str, float]]:
    """每次呼叫都重讀，方便使用者改 yaml 立刻生效，不用重啟 TUI。"""
    with open(_DATA_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("locations", {})


def _resolve_location(query: str, locations: Dict[str, Dict[str, float]]) -> str | None:
    """
    把使用者講的地名對應到 yaml 裡的正式名稱。
    先精確比對；再用雙向子字串比對（例如「應科」→「應科大樓」）。
    """
    q = query.strip()
    if not q:
        return None
    if q in locations:
        return q
    for name in locations:
        if q in name or name in q:
            return name
    return None


async def goto_skill(name: str) -> str:
    """送出指定地點 → JSON {x, y} → Isaac Sim。"""
    if not is_armed():
        return DISARMED_MSG

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


async def route_skill(start: str, goal: str) -> str:
    """
    「從 start 走到 goal」：
      1. 從 locations.yaml 查出起點/終點座標
      2. 發布 go_agent_route 指令到 command_topic（觸發同事那端跑路線）
      3. 把起點/終點座標印在對話欄位（給使用者確認）
    """
    if not is_armed():
        return DISARMED_MSG

    locations = _load_locations()
    start_name = _resolve_location(start, locations)
    goal_name = _resolve_location(goal, locations)

    missing = []
    if not start_name:
        missing.append(start)
    if not goal_name:
        missing.append(goal)
    if missing or start_name is None or goal_name is None:
        choices = "、".join(locations) or "（無）"
        return f"找不到地點：{'、'.join(missing)}。可用：{choices}"

    s = locations[start_name]
    g = locations[goal_name]

    # 發布 go_agent_route 觸發指令
    ros, err = safe_get_ros2()
    if not ros:
        pub_note = f"未發布 go_agent_route（ROS2 不可用：{err}）"
    else:
        topic = get_config().ros2.command_topic
        payload = json.dumps({"cmd": "go_agent_route"}, ensure_ascii=False)
        try:
            subs = await asyncio.to_thread(ros.publish_command, topic, payload)
            pub_note = f"已發布 go_agent_route → {topic}"
            if not subs:
                pub_note += "（注意：目前沒有訂閱者，訊息可能沒被接收）"
        except Exception as e:  # noqa: BLE001
            pub_note = f"發布 go_agent_route 失敗：{e}"

    return (
        f"路線：{start_name} → {goal_name}\n"
        f"  {start_name}: x={s['x']}, y={s['y']}\n"
        f"  {goal_name}: x={g['x']}, y={g['y']}\n"
        f"{pub_note}"
    )


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

_ROUTE_TOOL = {
    "type": "function",
    "function": {
        "name": "route",
        "description": (
            "Plan a route from a start location to a goal location (e.g. user says "
            "'從應科走到機械系館' / 'go from A to B'). Looks up both coordinates in "
            "locations.yaml, publishes the 'go_agent_route' command, and reports both "
            "coordinates back to the user."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "start": {"type": "string", "description": "Start location name."},
                "goal": {"type": "string", "description": "Goal location name."},
            },
            "required": ["start", "goal"],
        },
    },
}


def register_goto_skills() -> None:
    """TUI on_mount() 呼叫一次。"""
    register_skill(Skill("goto", "送出地點座標給 Isaac Sim", goto_skill, tool_schema=_GOTO_TOOL))
    register_skill(Skill("goto_list", "列出可用地點", goto_list_skill, tool_schema=_GOTO_LIST_TOOL))
    register_skill(Skill("route", "規劃路線並發布 go_agent_route", route_skill, tool_schema=_ROUTE_TOOL))
