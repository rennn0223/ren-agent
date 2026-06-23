# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/).

## [0.3.1] - 2026-06-24

### Added
- **車輛控制**：`/drive forward|back|left|right|stop [speed] [duration]`，自動發 `geometry_msgs/Twist` 到 `/cmd_vel`，duration 結束後自動補一筆 stop。
- **座標導航**：`/goto <地名>` 從 `src/ren_agent/data/locations.yaml` 取座標，包成 JSON `{"x": ..., "y": ...}` 用 `std_msgs/String` 發到 `/ren_agent/goal`。
- `/goto list` 列出所有可用地點。
- `/ros type <topic>`：顯示 topic 的訊息型別與欄位。
- `/ros pub <topic> <json>`：自動推斷型別 + `set_message_fields` 填欄位。
- **rclpy 單例 Node 管理器**（`tools/ros2_node.py`）：取代 subprocess，所有 ROS2 skill 共用一個 Node + executor thread + publisher cache。
- **Ollama Tool Calling**：`Skill` 加 `tool_schema` 欄位；`OllamaAgent.chat_stream` 變成 tool-call 迴圈（上限 5 輪）；TUI 顯示 `→ tool(args)` / `← result`。
- TUI welcome panel：兩欄式排版，banner 置中、整框 `Align.center`、`>` prompt prefix、focus 橘框、spinner 動畫。
- SlashMenu：白色指令名 + 深灰反白選取（Claude Code 風）。
- `/help` 改用 Rich Table 三欄對齊。
- 輸入 history 跨 session 持久化（`~/.config/ren-agent/history.txt`）。
- `Ros2Config`：`cmd_vel_topic`、`goal_topic` 可在設定檔覆寫。

### Changed
- ROS2 topic list / echo 從 subprocess 改為 rclpy（毫秒級延遲取代秒級）。
- `SLASH_COMMANDS` 改從 registry 動態產生，新增 skill 不用改 TUI。
- `__version__` 改用 `importlib.metadata.version("ren-agent")`，與 `pyproject.toml` 同步。
- `get_config()` 改單例，TUI 改模型後 skill 端看到同一份設定。
- system prompt 改為正體中文（保留程式碼/指令/topic 名稱原文）。
- `CommandContext` 加 `write_renderable(obj)`，讓 command handler 能輸出 Rich 物件。

### Removed
- `src/ren_agent/tools/ros2_cli.py`（subprocess 版死碼，已被 rclpy 取代）。
- `tests/test_ros2_cli.py`、`ROADMAP_AUDIT.md`、`pyproject.toml.bak`。
- `/q` 指令（純文字本來就會送給 LLM，沒必要）。
- `_sanitize_llm_output`（會誤吃掉模型正常輸出的 `A:` 開頭文字）。
- 寫死的 `SLASH_COMMANDS` / `HERO_VERSION`。

### Fixed
- `CommandContext.run_skill` 第一個參數從 `name` 改名 `skill`，避免 `run_skill("goto", name=...)` 跟 protocol 參數同名衝突。
- `ThinkingLine.visible` 改名 `active`，避免 override `Widget.visible`。

## [0.3.0] - 2026-06-23

### Added
- Slash commands registry。
- Skills registry。
- ROS2 CLI skills（subprocess 版）。
- `renagent connect` 一鍵啟動。
- 基礎測試覆蓋。
- README 更新為最新啟動方式與專案架構。

### Changed
- ROS2 相關實作改為獨立 skills 模組。
- TUI 由單一 chat app 擴充為 commands / skills 分層架構。
