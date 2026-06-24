"""
rclpy 單例 Node 管理器。

為什麼要單例：
  - subprocess 版（v0.3.0）每次 publish / list 都要 spawn `ros2` CLI，
    每次 1~3 秒延遲，跑 tool calling 時感覺很卡。
  - 改用 rclpy 後共用一個 Node + executor thread，連續發 100 條 Twist
    跟發 1 條一樣快。

為什麼要 lazy import：
  - rclpy 是系統 ROS2 安裝過後 source 才會出現，不在 pip / uv 依賴裡。
  - 直接 import 會讓沒裝 ROS2 的開發機（例如 Windows）整個程式起不來。
  - 改成在 Ros2Manager.__init__ 才 import，失敗就丟 Ros2Unavailable。

呼叫端統一用 safe_get_ros2() — 它會把 Ros2Unavailable 轉成 (None, msg) tuple，
避免每個 skill 都要寫 try/except。
"""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Any

# ── 單例狀態 ─────────────────────────────────────────
_lock = threading.Lock()
_instance: "Ros2Manager | None" = None


class Ros2Unavailable(RuntimeError):
    """rclpy 無法載入或 ROS2 環境未 source。"""


class Ros2Manager:
    """
    包裝一個長駐 rclpy Node。
    - get_topic_names_and_types / topic_type — 內省
    - get_publisher / publish / publish_json_string — 發布（publisher 會 cache）
    - echo_once — 一次性訂閱
    """

    # ── 初始化（lazy import + 起 executor thread）────
    def __init__(self) -> None:
        # 在 rclpy.init() 之前套用 ROS_DOMAIN_ID / RMW_IMPLEMENTATION，
        # 這兩個只有在 context 建立當下才會被讀取，所以一定要在 init 前設好。
        from ren_agent.core.config import get_config

        cfg = get_config()
        if cfg.ros2.domain_id is not None:
            os.environ["ROS_DOMAIN_ID"] = str(cfg.ros2.domain_id)
        if cfg.ros2.rmw_implementation:
            os.environ["RMW_IMPLEMENTATION"] = cfg.ros2.rmw_implementation

        try:
            import rclpy  # type: ignore[import-not-found]  # noqa: F401
            from rclpy.executors import SingleThreadedExecutor  # type: ignore[import-not-found]
            from rclpy.node import Node  # type: ignore[import-not-found]
        except ImportError as e:
            raise Ros2Unavailable(
                f"無法載入 rclpy：{e}。請先 source ROS2 環境。"
            )

        import rclpy as _rclpy  # type: ignore[import-not-found]

        # rclpy.init() 全 process 只能呼叫一次，重複呼叫會炸
        if not _rclpy.ok():
            _rclpy.init()

        self._rclpy = _rclpy
        self._node: Node = Node("ren_agent")
        self._executor = SingleThreadedExecutor()
        self._executor.add_node(self._node)

        # publisher cache：避免每次 publish 都 create_publisher
        # key = (topic, type_str)，value = rclpy Publisher
        self._publishers: dict[tuple[str, str], Any] = {}

        # ── Executor 跑在背景 daemon thread ──
        # 不然 subscription callback 不會被觸發
        self._shutdown = threading.Event()
        self._thread = threading.Thread(
            target=self._spin, name="ren-agent-ros2", daemon=True
        )
        self._thread.start()

    def _spin(self) -> None:
        """背景 thread 主迴圈：每 0.1 秒 spin 一次直到 shutdown。"""
        while not self._shutdown.is_set():
            try:
                self._executor.spin_once(timeout_sec=0.1)
            except Exception:
                # spin 出例外就退出（通常是 shutdown 中）
                break

    # ── Topic 內省 ───────────────────────────────────
    def topic_names_and_types(self) -> list[tuple[str, list[str]]]:
        """所有目前在 ROS graph 上看得到的 topic + 型別清單。"""
        return self._node.get_topic_names_and_types()

    def topic_type(self, topic: str) -> str | None:
        """查單一 topic 的訊息型別字串，例如 `geometry_msgs/msg/Twist`。"""
        for name, types in self.topic_names_and_types():
            if name == topic and types:
                return types[0]
        return None

    # ── Pub / Sub ────────────────────────────────────
    def _msg_class(self, type_str: str):
        """從 `package_name/msg/MsgName` 字串拿到 Python 類別。"""
        from rosidl_runtime_py.utilities import get_message  # type: ignore[import-not-found]
        return get_message(type_str)

    def get_publisher(self, topic: str, type_str: str):
        """取 cached publisher；不存在就建。QoS depth = 10。"""
        key = (topic, type_str)
        pub = self._publishers.get(key)
        if pub is None:
            msg_cls = self._msg_class(type_str)
            pub = self._node.create_publisher(msg_cls, topic, 10)
            self._publishers[key] = pub
        return pub

    def publish(self, topic: str, type_str: str, payload: dict) -> None:
        """
        通用 publish：dict → 對應訊息型別 → 發布。
        rosidl 的 set_message_fields 會自動把 dict 攤平塞進 msg 欄位
        （支援巢狀，例如 Twist 的 linear.x / angular.z）。
        """
        from rosidl_runtime_py.set_message import set_message_fields  # type: ignore[import-not-found]

        msg_cls = self._msg_class(type_str)
        msg = msg_cls()
        if payload:
            set_message_fields(msg, payload)
        pub = self.get_publisher(topic, type_str)
        pub.publish(msg)

    def publish_json_string(self, topic: str, json_payload: str) -> None:
        """
        把 JSON 字串包進 std_msgs/String.data 發出去。
        goto skill 用這個發座標給 Isaac Sim。
        """
        self.publish(topic, "std_msgs/msg/String", {"data": json_payload})

    def publish_command(
        self, topic: str, json_payload: str, wait_timeout: float = 2.0
    ) -> int:
        """
        發 std_msgs/String 指令，並仿照 `ros2 topic pub --wait-matching-subscriptions 1`：
        先等到至少一個訂閱者（最多 wait_timeout 秒）再發布，降低訊息漏接。

        回傳發布當下的訂閱者數量（0 代表沒人在聽，呼叫端可據此提示使用者）。
        """
        from rosidl_runtime_py.set_message import set_message_fields  # type: ignore[import-not-found]

        type_str = "std_msgs/msg/String"
        pub = self.get_publisher(topic, type_str)

        deadline = time.monotonic() + max(0.0, wait_timeout)
        while pub.get_subscription_count() < 1 and time.monotonic() < deadline:
            time.sleep(0.05)

        msg = self._msg_class(type_str)()
        set_message_fields(msg, {"data": json_payload})
        pub.publish(msg)
        return pub.get_subscription_count()

    def echo_once(self, topic: str, timeout: float = 3.0) -> str | None:
        """
        訂閱一次，收到第一個訊息就取消 subscription，回傳 YAML 字串。
        topic 不存在 / timeout 內沒人發布 → 回 None。
        """
        type_str = self.topic_type(topic)
        if not type_str:
            return None
        msg_cls = self._msg_class(type_str)

        from rosidl_runtime_py import message_to_yaml  # type: ignore[import-not-found]

        got: dict[str, Any] = {}   # 用 dict 包裝才能在 callback 裡寫入
        evt = threading.Event()    # 收到訊息就 set，主執行緒 wait

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
            # 不管成功與否都要解掉訂閱，避免泄漏
            self._node.destroy_subscription(sub)

    # ── 型別描述 ─────────────────────────────────────
    def describe_type(self, type_str: str) -> str:
        """
        把 msg 型別印成人類可讀的欄位清單。
        範例：
          geometry_msgs/msg/Twist
            geometry_msgs/Vector3 linear
            geometry_msgs/Vector3 angular
        """
        msg_cls = self._msg_class(type_str)
        # get_fields_and_field_types 是 rosidl 自動產生的 classmethod
        fields: dict[str, str] = getattr(msg_cls, "get_fields_and_field_types", lambda: {})()
        if not fields:
            return f"{type_str}（無欄位資訊）"
        lines = [f"{type_str}"]
        for name, ftype in fields.items():
            lines.append(f"  {ftype} {name}")
        return "\n".join(lines)

    # ── 生命週期 ─────────────────────────────────────
    def shutdown(self) -> None:
        """目前 TUI 不主動呼叫，靠 process 退出時 daemon thread 自然死。"""
        self._shutdown.set()
        try:
            self._executor.shutdown()
        except Exception:
            pass
        try:
            self._node.destroy_node()
        except Exception:
            pass


# ── 外部存取單例 ────────────────────────────────────
def get_ros2() -> Ros2Manager:
    """取得（或建立）單例 Ros2Manager。失敗會丟 Ros2Unavailable。"""
    global _instance
    with _lock:
        if _instance is None:
            _instance = Ros2Manager()
        return _instance


def safe_get_ros2() -> tuple[Ros2Manager | None, str | None]:
    """非例外版本：失敗回傳 (None, 錯誤訊息)。給 skill 用方便。"""
    try:
        return get_ros2(), None
    except Ros2Unavailable as e:
        return None, str(e)


def reinit_ros2(domain_id: int | None = None, rmw: str | None = None) -> Ros2Manager:
    """
    用新的 ROS_DOMAIN_ID / RMW 重建 ROS2 node。

    因為 domain / rmw 只在 rclpy context 建立時生效，要動態切換就得：
      1. 把新值寫進 config（後續建立 node 時會讀）
      2. 關掉舊 node 與 rclpy context
      3. 重新建立單例（__init__ 會用新 env 重新 init）

    失敗會丟 Ros2Unavailable。
    """
    from ren_agent.core.config import get_config

    cfg = get_config()
    if domain_id is not None:
        cfg.ros2.domain_id = domain_id
    if rmw is not None:
        cfg.ros2.rmw_implementation = rmw

    global _instance
    with _lock:
        old = _instance
        _instance = None
        if old is not None:
            old.shutdown()
        # 關掉 rclpy context，下次 init 才能套用新 domain
        try:
            import rclpy  # type: ignore[import-not-found]

            if rclpy.ok():
                rclpy.shutdown()
        except Exception:
            pass

    # 在 lock 外呼叫（get_ros2 會自己拿 lock），用新設定重建
    return get_ros2()


# ── 公用小工具 ──────────────────────────────────────
def ensure_json_dict(payload: str | dict) -> dict:
    """skill 端的 payload 可能是 dict 也可能是 JSON 字串，統一轉成 dict。"""
    if isinstance(payload, dict):
        return payload
    return json.loads(payload)
