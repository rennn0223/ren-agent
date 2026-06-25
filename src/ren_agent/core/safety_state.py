"""
車輛 arm/disarm 安全閂（process 級單例狀態）。

設計理念（借鏡無人機 / 工業機器人）：
  - 車輛預設 **disarmed**（上鎖）。任何「會讓車移動」的 skill
    （drive / goto / route / agent_command）在 disarmed 時一律拒絕執行。
  - 使用者必須明確 `/arm` 解鎖，才代表「我人在場、確認可以動」。
  - E-stop 會 disarm（latch）：緊急停止後必須重新 arm 才能再動，
    避免「停了之後又被一個殘留指令帶跑」。

這層閂同時擋住兩條執行路徑：斜線指令與 LLM tool-call，
因為檢查放在 skill 執行層（不是 UI 層）。
"""
from __future__ import annotations

import threading

_lock = threading.Lock()
_armed = False

# 統一的拒絕訊息，移動類 skill 共用。
DISARMED_MSG = "🔒 車輛未解鎖（disarmed）。請先 `/arm` 解鎖才能移動。"


def is_armed() -> bool:
    """目前是否已解鎖（可移動）。"""
    return _armed


def arm() -> None:
    """解鎖：允許移動類指令執行。"""
    global _armed
    with _lock:
        _armed = True


def disarm() -> None:
    """上鎖：拒絕一切移動類指令（E-stop / 關閉時呼叫）。"""
    global _armed
    with _lock:
        _armed = False
