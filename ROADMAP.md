# ren-agent 開發路線圖

> 勾選代表「已完成」，未勾選的是「下一步或規劃中」。

***

## ✅ v0.1.0 — 基礎 TUI + Ollama Chat

- [x] 使用 Textual 建立 TUI 主架構
- [x] 整合 Ollama Python Client，支援本機模型對話
- [x] 實作非同步串流回應
- [x] 設計 REN AGENT ASCII banner
- [x] 加入臘腸狗吉祥物
- [x] 支援斜線指令：`/help`、`/clear`、`/model`、`/bye`
- [x] 設定 Ruff / mypy / pytest + uv 指令
- [x] 第一個穩定版 commit & push（master 分支）

***

## ✅ v0.2.0 — ROS2 整合與車載基礎能力

- [x] ROS2 topic 探索工具
  - [x] `/ros topics` 列出可用 topic
  - [x] `/ros echo <topic>` 單次讀取並顯示資料格式
- [x] 將 ROS2 工具整合為獨立模組（subprocess 版）
- [x] 增加簡單錯誤提示

***

## ✅ v0.3.0 — 開發體驗與擴充性

- [x] Slash commands 擴充機制（registry）
- [x] Skills 模組介面（`Skill` / `run_skill`）
- [x] TUI 體驗小改：輸入 history 快捷鍵、SlashMenu 上下鍵選取 + Tab 補全、回合制排隊對話
- [x] 一鍵啟動：`python -m ren_agent.tui.main` / `renagent connect`
- [x] 基礎單元測試（config / commands / ollama mock）

***

## ✅ v0.3.1 — rclpy 化、車輛控制、Tool Calling、Claude Code 風 TUI

- [x] **rclpy 化**：拋棄 subprocess，改用單例 `Ros2Manager`（Node + executor thread）
  - [x] 共用 publisher cache
  - [x] `topic_names_and_types` / `topic_type` / `echo_once` 統一 API
- [x] **車輛控制**：`/drive forward|back|left|right|stop [speed] [duration]`
  - [x] 自動 stop（duration 結束）
  - [x] `cmd_vel_topic` 可在設定檔覆寫
- [x] **座標導航**：`/goto <地名>` → JSON `{x, y}` → Isaac Sim
  - [x] `locations.yaml` 預載應科大樓、機械系館
  - [x] `goal_topic` 預設 `/ren_agent/goal`（`std_msgs/String`）
- [x] **ROS2 訊息推斷與發布**
  - [x] `/ros type <topic>`：顯示型別與欄位
  - [x] `/ros pub <topic> <json>`：自動推斷型別 + `set_message_fields`
- [x] **Ollama Tool Calling**
  - [x] `Skill` 加 `tool_schema` 欄位
  - [x] `OllamaAgent.chat_stream` 支援 tools 迴圈（上限 5 輪）
  - [x] TUI 顯示 `→ tool({...})` / `← 結果`
- [x] **Claude Code 風 TUI**
  - [x] Welcome panel：banner 置中、左欄 mascot/meta、右欄 Tips / Recent activity
  - [x] 整框 `Align.center` 置中
  - [x] Spinner 動畫、focus 橘框、`>` prompt prefix
  - [x] SlashMenu：白色指令名 + 深灰反白選取
  - [x] `/help` 改用 Rich Table（三欄對齊）
  - [x] 輸入 history 持久化（`~/.config/ren-agent/history.txt`）
- [x] **system prompt 改正體中文**
- [x] 清理：刪 `tools/ros2_cli.py`、`/q` 指令、`_sanitize_llm_output`
- [x] 版本同步：`__version__` 改用 `importlib.metadata`

***

## 📋 v0.4.0 — Isaac Sim 實戰

- [ ] Isaac Sim 端寫一個 subscriber 接 `/ren_agent/goal`
- [ ] 把 `locations.yaml` 從經緯度換成 Isaac Sim 本地 frame（meter）
- [ ] `/drive` 改可由 LLM 動態調速（依環境提示降速）
- [ ] `goto` 加路徑回報（reached / blocked / replanned）
- [ ] TUI 即時顯示車輛當前位置（subscribe `/odom`）

***

## 📋 v0.5.0 — 多車與安全

- [ ] 多 namespace 支援（`/robot_1/cmd_vel`、`/robot_2/cmd_vel`）
- [ ] SLAM 地圖 hook：列出已知地點、加新地點
- [ ] 安全層：emergency stop topic、超時自動停車
- [ ] 簡易 telemetry：電量 / 速度 / 障礙物距離

***

## 📦 維運與品質（持續進行）

- [ ] CI：GitHub Actions（ruff / mypy / pytest）
- [ ] 標籤 release 時自動 build wheel
- [x] CHANGELOG 跟著版本走
- [ ] README 補一張 TUI 截圖
- [ ] `CONTRIBUTING.md`
