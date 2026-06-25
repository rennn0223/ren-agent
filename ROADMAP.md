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

## ✅ v0.3.2 — 路線規劃、動態 ROS domain、Markdown 渲染

- [x] **路線規劃**：`/route <起點> <終點>`（與自然語言「從應科走到機械系館」）
  - [x] 查 `locations.yaml` 兩端座標、發布 `go_agent_route`、把座標印到對話欄位
  - [x] 地名支援簡稱（雙向子字串比對）
- [x] **動態 ROS domain**：`/domain <id> [rmw]` 切換 `ROS_DOMAIN_ID` / `RMW` 並重建 node
- [x] **Agent 指令**：`/agent [cmd]` 發 `std_msgs/String` JSON 到 `/ai_agent/command`（先等訂閱者）
- [x] `route` / `set_domain` / `agent_command` skill + tool schema
- [x] `core/context.py`（token 估算 + StatusBar 用量）、`core/files.py`（`@` mention）
- [x] TUI：ESC 中斷、Shift+Tab 模式切換、Ctrl+R 展開、動態 spinner
- [x] 助手回覆 Markdown 即時渲染、welcome panel 隨 resize 動態置中
- [x] ROS2 humble → jazzy、新增 `numpy` 依賴

***

> 📐 **規劃原則**：自 v0.4.0 起，依 [MATURITY.md](./MATURITY.md) 的安全優先順序推進
> （**安全 > 可靠 > 可測試 > 模塊化 > 可維護 > 好用**）。
> LLM 只負責「意圖」，執行層必須有確定性的安全閘門。
> **v1.0.0 = 安全層全綠 + SIL 驗證 + 可觀測 + Security + CI/CD + 文件齊備 → 可上線。**

***

## 🛡️ v0.4.0 — 安全層（Safety-critical，最高優先）

> 對應 MATURITY 第一層。這是從「Demo / 工具」走向「可控實體車」最關鍵的一步。

- [x] **執行層速度上限夾限**：`/drive` 在發 `Twist` 前把線/角速度 clamp 到 `SafetyConfig` 上限並透明回報
- [x] **緊急停止 E-stop**：Ctrl+X / `/estop` / 自然語言，立即送 0 速度 + E-stop 訊號，取消串流並 latch 上鎖
- [x] **移動限時 watchdog**：`max_drive_duration` 上限，不允許無限驅動，車一定在上限內自動停
- [x] **失效安全 fail-safe**：TUI 關閉時 best-effort 送停車並上鎖；agent 卡住由 watchdog 兜底
- [x] **arm / disarm 安全閂**：車輛預設上鎖，移動類 skill 未 `/arm` 一律拒絕（擋斜線 + LLM tool-call 兩路）；狀態列常駐 ARMED/DISARMED 徽章
- [x] **LLM↔執行層驗證閘門**：封閉動作集（已註冊 tool schema）+ 各 skill 參數驗證 + 速度夾限 + arm 閂 + 萬用發佈人工批准
- [x] **萬用發佈人工批准閘門（v0.4.2，approval-engine 雛形）**：`ros_publish` 由 LLM 觸發時登記成待批准動作，須 `/approve` 才執行、`/reject` 取消；手打 `/ros pub` 直送。`core/approvals.py`
- [x] **安全邏輯自動化測試**：速度夾限 / watchdog / E-stop / arm 閂 / 批准閘門皆有測試
- [x] **安全參數外部化**：`SafetyConfig`（max_linear/angular_speed、max_drive_duration、estop_topic）
- [ ] **加速度（斜率）限制**：避免瞬間全速（⏳ 後續）
- [ ] **接收端心跳超時停車**：>300ms 未更新自動停（⏳ 需 Sim/實車端配合）
- [ ] **地理圍欄 geofence**：移至 v0.5（需要 `/odom` 車輛定位才有意義）

***

## 📡 v0.5.0 — 可靠性、可觀測性與 Isaac Sim 實戰

> 對應 MATURITY 第二、四層。

### 🧹 v0.4.2 review 留下的待辦（已排入 v0.5）
- [ ] **`route_skill` payload 帶起點/終點座標**（目前所有 `/route` 都送同一個 `{"cmd":"go_agent_route"}`，下游無法分辨不同路線）— 需要與同事的接收端對齊新 schema 後一起做
- [ ] **approval gate 升級為 Skill 級宣告**：`Skill` 加 `requires_approval` 欄位，由 `run_skill` 統一在 LLM 路徑包 `request_approval`，取代目前只在 `ros_publish` 手寫的閘門（讓 `agent_command` 等高風險動作也能 opt-in）
- [ ] **arm-check 收斂進 `run_skill`**：`Skill` 加 `requires_armed` 欄位，在 dispatch 層統一檢查，移除 `drive`/`goto`/`route`/`agent_command` 四處複製貼上的 `if not is_armed(): return DISARMED_MSG`
- [ ] **Topic policy 在 `Ros2Manager.publish` 層做**：對 `cmd_vel` topic 一律套 Twist 夾限（目前在 `drive_skill` 跟 `ros_publish_skill` 分別做了一次），把安全閘門收到實際的 publish boundary
- [ ] **未接線模組接上或移除**：`core/files.py`（`@` mention）、`core/context.py`（token 計數）目前有測試但 TUI 沒呼叫

### 主線
- [ ] **規則式風險分數分級**：approval-engine 從「萬用發佈強制批准」擴充為 Low/Medium/High 規則式風險分數（依 topic、`/depth` 障礙、`/odom` 移動中、近期 error log、模型信心等加權），決定直送 / 提案 / 強制批准
- [ ] **車輛狀態機**：idle / moving / stopped / error，作為指令仲裁基礎
- [ ] **動作完成回報**：`goto` / `route` 回報 reached / blocked / replanned
- [ ] **多指令衝突處理**：移動中收到新指令的仲裁規則（佇列 / 搶佔 / 拒絕）
- [ ] **重連 / 重試策略**：Ollama 或 ROS2 短暫中斷後自動恢復
- [ ] **稽核軌跡 audit trail**：自然語言輸入 → LLM 決策 → 實際 ROS2 訊息全程可追溯、可回放
- [ ] **TUI 即時車輛狀態**：subscribe `/odom` 顯示位置 / 速度
- [ ] **地理圍欄 geofence**：有了 `/odom` 定位後，超出工作區邊界拒絕移動（自 v0.4.0 移入）
- [ ] **Isaac Sim 串接**：Sim 端 subscriber 接 `/ren_agent/goal`
- [ ] `locations.yaml` 改用 Isaac Sim 本地 frame（meter）
- [ ] **SIL（模擬器在環）測試**：Sim 跑通「自然語言 → 移動 → 到達回報」完整流程

***

## 🔐 v0.6.0 — Security、部署與 CI/CD

> 對應 MATURITY 第六、五、九層。

- [ ] **控車指令存取控制**：誰可以下指令（車控網路暴露 = 遠端遙控實體車）
- [ ] **ROS2 網路隔離 / 認證**（SROS2 或網段隔離）
- [ ] **GitHub Actions CI**：PR 自動跑 ruff / mypy / pytest
- [ ] 受保護分支 + PR review 規則
- [ ] release 自動 build wheel
- [ ] 容器化 / 服務化部署（Docker 或 systemd）+ 部署文件

***

## 🚗 v0.7.0 — 多車與進階能力

- [ ] 多 namespace 支援（`/robot_1/cmd_vel`、`/robot_2/cmd_vel`）
- [ ] SLAM 地圖 hook：列出已知地點、新增地點
- [ ] 簡易 telemetry：電量 / 速度 / 障礙物距離
- [ ] `/drive` 由 LLM 依環境提示動態調速（在安全夾限內）

***

## 🏁 v1.0.0 — 可上線（Definition of Done）

> 達成 [MATURITY.md](./MATURITY.md) 全部出場條件才視為完善可上線。

- [ ] 安全層全綠（v0.4.0 全部完成 + 測試）
- [ ] 可靠性：狀態機 + 動作回報 + 重連策略
- [ ] 可觀測性：完整稽核軌跡 + 即時車輛狀態
- [ ] SIL 驗證 + 實車驗證通過
- [ ] Security：存取控制 + 網路隔離
- [ ] CI/CD：PR 自動檢查 + 受保護分支
- [ ] 文件：架構圖 + 操作員安全手冊 + 開發指南

***

## 📦 維運與品質（持續進行）

- [x] CHANGELOG 跟著版本走
- [x] 語意化版本 + git tag + GitHub Release
- [x] 專案成熟度自評表（[MATURITY.md](./MATURITY.md)）
- [ ] CI：GitHub Actions（ruff / mypy / pytest）
- [ ] 標籤 release 時自動 build wheel
- [ ] README 補一張 TUI 截圖
- [ ] 架構圖（資料流：使用者 → LLM → skill → ROS2 → 車）
- [ ] `CONTRIBUTING.md` + 「如何新增一個 skill」開發指南
- [ ] 操作員安全手冊（實車操作前必讀）
