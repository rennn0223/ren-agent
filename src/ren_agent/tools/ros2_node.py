"""
rclpy 單例 Node 管理器。

所有 ROS2 skill 共用同一個 Node + executor thread，避免每次 subprocess
spawn 的延遲。rclpy 是 lazy import，因為開發機可能沒裝 ROS2。
"""
from __future__ import annotations

import json
import threading
from typing import Any

_lock = threading.Lock()
_instance: "Ros2Manager | None" = None


class Ros2Unavailable(RuntimeError):
    """rclpy 無法載入或 ROS2 環境未 source。"""


class Ros2Manager:
    def __init__(self) -> None:
        try:
            import rclpy  # type: ignore[import-not-found]  # noqa: F401
            from rclpy.executors import SingleThreadedExecutor  # type: ignore[import-not-found]
            from rclpy.node import Node  # type: ignore[import-not-found]
        except ImportError as e:
            raise Ros2Unavailable(
                f"無法載入 rclpy：{e}。請先 source ROS2 環境。"
            )

        import rclpy as _rclpy  # type: ignore[import-not-found]

        if not _rclpy.ok():
            _rclpy.init()

        self._rclpy = _rclpy
        self._node: Node = Node("ren_agent")
        self._executor = SingleThreadedExecutor()
        self._executor.add_node(self._node)

        self._publishers: dict[tuple[str, str], Any] = {}
        self._shutdown = threading.Event()
        self._thread = threading.Thread(
            target=self._spin, name="ren-agent-ros2", daemon=True
        )
        self._thread.start()

    def _spin(self) -> None:
        while not self._shutdown.is_set():
            try:
                self._executor.spin_once(timeout_sec=0.1)
            except Exception:
                break

    # ── Introspection ──────────────────────────────────────

    def topic_names_and_types(self) -> list[tuple[str, list[str]]]:
        return self._node.get_topic_names_and_types()

    def topic_type(self, topic: str) -> str | None:
        for name, types in self.topic_names_and_types():
            if name == topic and types:
                return types[0]
        return None

    # ── Pub / Sub ──────────────────────────────────────────

    def _msg_class(self, type_str: str):
        from rosidl_runtime_py.utilities import get_message  # type: ignore[import-not-found]
        return get_message(type_str)

    def get_publisher(self, topic: str, type_str: str):
        key = (topic, type_str)
        pub = self._publishers.get(key)
        if pub is None:
            msg_cls = self._msg_class(type_str)
            pub = self._node.create_publisher(msg_cls, topic, 10)
            self._publishers[key] = pub
        return pub

    def publish(self, topic: str, type_str: str, payload: dict) -> None:
        from rosidl_runtime_py.set_message import set_message_fields  # type: ignore[import-not-found]

        msg_cls = self._msg_class(type_str)
        msg = msg_cls()
        if payload:
            set_message_fields(msg, payload)
        pub = self.get_publisher(topic, type_str)
        pub.publish(msg)

    def publish_json_string(self, topic: str, json_payload: str) -> None:
        """把 JSON 字串包進 std_msgs/String.data 發出去（Isaac Sim 用）。"""
        self.publish(topic, "std_msgs/msg/String", {"data": json_payload})

    def echo_once(self, topic: str, timeout: float = 3.0) -> str | None:
        """訂閱一次後立刻取消。回傳 message 的 yaml 字串。"""
        type_str = self.topic_type(topic)
        if not type_str:
            return None
        msg_cls = self._msg_class(type_str)

        from rosidl_runtime_py import message_to_yaml  # type: ignore[import-not-found]

        got: dict[str, Any] = {}
        evt = threading.Event()

        def _cb(msg):
            if "msg" not in got:
                got["msg"] = msg
                evt.set()

        sub = self._node.create_subscription(msg_cls, topic, _cb, 10)
        try:
            if not evt.wait(timeout):
                return None
            return message_to_yaml(got["msg"])
        finally:
            self._node.destroy_subscription(sub)

    # ── Type 描述 ──────────────────────────────────────────

    def describe_type(self, type_str: str) -> str:
        msg_cls = self._msg_class(type_str)
        fields: dict[str, str] = getattr(msg_cls, "get_fields_and_field_types", lambda: {})()
        if not fields:
            return f"{type_str}（無欄位資訊）"
        lines = [f"{type_str}"]
        for name, ftype in fields.items():
            lines.append(f"  {ftype} {name}")
        return "\n".join(lines)

    # ── 生命週期 ───────────────────────────────────────────

    def shutdown(self) -> None:
        self._shutdown.set()
        try:
            self._executor.shutdown()
        except Exception:
            pass
        try:
            self._node.destroy_node()
        except Exception:
            pass


def get_ros2() -> Ros2Manager:
    """取得（或建立）單例 Ros2Manager。"""
    global _instance
    with _lock:
        if _instance is None:
            _instance = Ros2Manager()
        return _instance


def safe_get_ros2() -> tuple[Ros2Manager | None, str | None]:
    """非例外版本：失敗回傳 (None, 錯誤訊息)。"""
    try:
        return get_ros2(), None
    except Ros2Unavailable as e:
        return None, str(e)


# 工具：給 skill 用
def ensure_json_dict(payload: str | dict) -> dict:
    if isinstance(payload, dict):
        return payload
    return json.loads(payload)
