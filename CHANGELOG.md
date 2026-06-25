# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/).

## [0.4.1] - 2026-06-25

### Changed（TUI）
- **Welcome 面板改版（Claude Code 風）**：左欄置中（臘腸狗吉祥物 + `Welcome back!` + 模型 / 路徑），中間垂直分隔線，右欄 Tips → 細分隔線 → Recent activity；圓角外框、左上標題。提示更新為 `/arm` → `/drive`、`Ctrl+X` 急停。面板隨終端寬度撐滿並自動重繪。
- 移除開場大型 ASCII banner（保留臘腸狗）。

### Fixed（TUI）
- **Slash 指令選單可捲動**：原本只顯示視窗內前幾個指令、方向鍵看不到其餘；改為捲動視窗，`↑↓` 可瀏覽全部指令，並顯示位置指示（`↑↓ n/total`）。
- 修正 `Panel(expand=False)` 重新量測會把 `no_wrap` 臘腸狗截頭的問題（改用 `expand=True` + 固定左欄寬）。

### Fixed（ROS2）
- **修正關閉時 `terminate called without an active exception`**：程式結束 / `/domain` 切換時未乾淨關閉 rclpy，導致底層 DDS C++ thread 被亂序解構。`Ros2Manager.shutdown()` 改為先 join spin thread 再拆 node；新增 `shutdown_ros2()` 關閉 rclpy context，TUI `on_unmount` 送完 fail-safe 停車後呼叫。

## [0.4.0] - 2026-06-25

### Added（安全層）
- **執行層速度夾限**：新增 `SafetyConfig`（`max_linear_speed` 預設 0.5 m/s、`max_angular_speed` 預設 1.0 rad/s）。`/drive` 發 `Twist` 前一律把線速度 / 角速度硬夾限到上限，避免 LLM 或使用者傳入失控速度；被夾限時於回覆中透明標註。
- **緊急停止 E-stop**：`Ctrl+X` 快捷鍵 / `/estop`（alias `/stop`）/ 自然語言「緊急停止、停下來」→ 立即送 0 速度到 `cmd_vel`，並 best-effort 發 `std_msgs/Bool` True 到 `safety.estop_topic`（預設 `/ren_agent/estop`）；同時取消進行中的 LLM 串流與佇列。新增 `tools/safety.py`。
- **移動時間 watchdog**：新增 `SafetyConfig.max_drive_duration`（預設 5.0s）。`/drive` 不再允許「無限驅動」，`duration<=0` 或超過上限都夾到上限，確保車一定會在上限內自動停。
- **關閉 fail-safe**：TUI 關閉（`on_unmount`）時 best-effort 送一筆停車（`safety.stop_now`），避免離開後車維持最後速度。
- **arm / disarm 安全閂**：新增 `core/safety_state.py`。車輛預設上鎖，移動類 skill（drive/goto/route/agent_command）未 `/arm` 一律拒絕（同時擋斜線指令與 LLM tool-call）。`/arm`、`/disarm` 指令；E-stop 與關閉 fail-safe 會 latch 上鎖。狀態列常駐 `● ARMED` / `● DISARMED` 徽章。

## [0.3.3] - 2026-06-25

### Docs
- 新增 `MATURITY.md`：專案成熟度自評表（可打勾），以「安全優先」分十層，定義 v1.0.0 上線出場條件。
- 重寫 `ROADMAP.md`：自 v0.4.0 起依安全優先順序推進（v0.4.0 安全層 → v0.5.0 可靠/可觀測/Isaac Sim → v0.6.0 Security/CI/CD → v0.7.0 多車 → v1.0.0 可上線）。
- `README.md`：版本表更新、加入安全須知與 `MATURITY.md` 連結。

## [0.3.2] - 2026-06-24

### Added
- **路線規劃**：`/route <起點> <終點>`（或自然語言「從應科走到機械系館」）— 查 `locations.yaml` 兩端座標、發布 `go_agent_route`，並把起點/終點座標印到對話欄位。地名支援簡稱（雙向子字串比對）。
- **動態 ROS domain**：`/domain <id> [rmw]` 動態切換 `ROS_DOMAIN_ID` / `RMW_IMPLEMENTATION` 並重建 rclpy node。
- **Agent 指令**：`/agent [cmd]`（預設 `go_agent_route`）發 `std_msgs/String` JSON 到 `/ai_agent/command`，仿 `--wait-matching-subscriptions` 先等訂閱者再發。
- `route` / `set_domain` / `agent_command` skill + tool schema，LLM 可自主呼叫。
- `core/context.py`：token 估算，StatusBar 顯示 context 用量。
- `core/files.py`：專案檔索引 + `@` mention 展開，輸入框 AtMenu 補全。
- TUI：ESC 中斷串流、Shift+Tab 模式切換 + ModeBar、Ctrl+R 展開工具輸出、ThinkingLine 動態 spinner（秒數 / token）。
- 助手回覆改 **Markdown 即時渲染**（橘色 ● bullet + hanging indent），串流中即時格式化。
- welcome panel 隨終端 resize **動態水平置中**（`expand=True` + `on_resize` 重畫）。

### Changed
- ROS2 發行版從 humble 改為 **jazzy**（`scripts/renagent`、README）。
- `Ros2Manager` 在 `rclpy.init()` 前套用 domain / rmw；新增 `publish_command`（等待訂閱者）與 `reinit_ros2`。
- 新增 `numpy>=1.26,<2` 依賴（rclpy 需要，且需相容 Jazzy 的 numpy 1.x ABI）。

### Fixed
- `run_skill` 第一參數改 positional-only，修 `run_skill("goto", name=...)` 的參數同名衝突。
- `scripts/renagent` source ROS 前暫關 `set -u/-e`，修 `AMENT_TRACE_SETUP_FILES: unbound variable`。
- `/goto <地名>` 後輸入參數時 Enter 送不出去（SlashMenu 攔截）。

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
