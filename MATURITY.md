# ren-agent 專案成熟度自評表

> 目標：**v1.0.0 = 真正可上線、可控實體車的產品**。
> 勾選 = 已完成且有測試／驗證；未勾 = 待辦（我們再一起做）。
>
> 目前版本：**v0.3.3**　｜　最後更新：2026-06-25

## 圖例

- `[x]` 已完成
- `[~]` 部分完成（說明寫在後面）
- `[ ]` 未開始

## 優先級總原則

> 一般軟體追求「功能正確」；車控 Agent 追求「即使出錯也安全」。
> 優先級：**安全 > 可靠 > 可測試 > 模塊化 > 可維護 > 好用**。
> LLM 的定位是「會講人話的意圖翻譯器」，**不是最終決策者**——它與執行層之間一定要有一道確定性的安全閘門。

---

## 第一層：安全層（Safety-critical，上線前不可妥協）

> 這是車控專案跟一般軟體最大的差別，也是目前 ren-agent 最大的缺口。

- [ ] **緊急停止 E-stop**：任何狀態下可立即停車，優先級高於一切指令（鍵盤快捷鍵 + topic）
- [ ] **失效安全 fail-safe**：LLM 當掉 / 連線斷 / 收不到訊號 → 預設「停車」，而非維持上一動作
- [ ] **看門狗 watchdog / 心跳**：`/cmd_vel` 超時（例如 >300ms 未更新）自動發 stop
- [~] **速度 / 加速度上限夾限**：✅ 線速度 / 角速度已在執行層硬夾限（`SafetyConfig.max_linear_speed` / `max_angular_speed`，發 Twist 前 clamp 並透明回報）；⏳ 加速度（斜率）限制尚未做
- [ ] **地理圍欄 geofence / 工作區邊界**：超出允許範圍拒絕移動
- [~] **LLM 與執行層之間的驗證閘門**：skill 已驗證輸入（route 找不到地點、domain 範圍檢查）+ 速度已硬夾限；⏳ 仍**未限制可執行動作集**
- [ ] **危險／不可逆動作需人工確認**：plan / auto-accept 模式目前只是 UI 指示，**未真正攔截執行**
- [ ] **安全邏輯的自動化測試**：超速被擋、超時停車、E-stop 生效都要有測試覆蓋

---

## 第二層：可靠性與確定性

- [x] ROS2 訊息發布前等待訂閱者（`publish_command` 仿 `--wait-matching-subscriptions`）
- [~] **指令冪等 / 可預期**：一般 skill 可預期，但缺少車輛「狀態機」（idle / moving / stopped / error）
- [ ] **重連 / 重試策略**：Ollama 或 ROS2 短暫中斷後的自動恢復
- [ ] **動作完成回報**：goto / route 的 reached / blocked / replanned 狀態回饋
- [ ] **多指令衝突處理**：移動中收到新移動指令的仲裁規則（佇列 vs 搶佔 vs 拒絕）

---

## 第三層：工程品質

### 模塊化 / 架構

- [x] UI / Agent 推理 / Skills / ROS2 中介解耦
- [x] Skills / Commands registry（新增能力不用改 TUI）
- [x] ROS2 單例 Node 管理器（共用 Node + executor + publisher cache）
- [~] **模擬與實車共用同一套 skill**：架構支援，但尚未抽象出明確的「控制後端介面」

### 可測試性

- [x] 純邏輯可在無 ROS2 / 無實車下單元測試（mock）
- [x] 測試涵蓋：config / commands / skills / context / files / route / ROS2 指令 / TUI 送出
- [ ] **模擬器在環（SIL）測試**：Isaac Sim 跑完整流程
- [ ] **安全邏輯測試**（見第一層）
- [ ] 測試覆蓋率門檻（coverage gate）

### 可維護性 / 可讀性

- [x] 「為什麼」導向的中文區塊註解
- [x] 型別註記 + mypy 全通過
- [x] Ruff lint 全通過
- [x] 小而專注的函式 / 一致命名

---

## 第四層：可觀測性（車控 debug 生命線）

- [x] 基礎日誌（loguru，stderr + 檔案）
- [ ] **稽核軌跡 audit trail**：每個指令「自然語言輸入 → LLM 決策 → 實際發出的 ROS2 訊息」全程可追溯、可回放
- [~] **即時狀態顯示**：狀態列有連線 / token，但**無車輛位置 / 速度**
- [ ] 車輛即時位置（subscribe `/odom`）顯示在 TUI
- [ ] 關鍵事件指標（指令數 / 失敗率 / 平均延遲）

---

## 第五層：設定與部署

- [x] topic 名稱 / domain / RMW 可由設定檔覆寫（`Ros2Config`）
- [x] 地點表外部化（`locations.yaml`，可熱改）
- [x] 動態切換 ROS_DOMAIN_ID / RMW（`/domain`）
- [ ] **速度上限 / 安全參數外部化**（max_speed、watchdog timeout、geofence 範圍）
- [x] 一鍵啟動（`renagent connect` 自動 source ROS2）
- [ ] 容器化 / 部署文件（Docker 或 systemd 服務化）

---

## 第六層：安全性 / 權限（Security）

- [ ] **控車指令的存取控制**：誰可以下指令（車控網路暴露 = 遠端遙控實體車）
- [ ] ROS2 網路隔離 / 認證（SROS2 或網段隔離）
- [ ] 機密管理（若未來接雲端 / API key）

---

## 第七層：錯誤處理與降級

- [x] ROS2 不可用 → 清楚訊息而非崩潰
- [x] 地點找不到 / 訂閱者不在 → 可行動的提示
- [ ] LLM 逾時 / 工具呼叫失敗的統一降級策略
- [ ] 使用者可理解的錯誤碼 / 故障排除指引

---

## 第八層：文件與可上手性

- [x] README（安裝 / 使用 / 功能）
- [x] CHANGELOG（跟著版本走）
- [x] ROADMAP
- [ ] **架構圖**（資料流：使用者 → LLM → skill → ROS2 → 車）
- [ ] **「如何新增一個 skill」開發指南**
- [ ] `CONTRIBUTING.md`
- [ ] README 補 TUI 截圖 / Demo 影片
- [ ] 安全須知 / 操作員手冊（實車操作前必讀）

---

## 第九層：CI/CD 與版本紀律

- [x] 語意化版本 + git tag + GitHub Release
- [x] 本地可跑 ruff / mypy / pytest
- [ ] **GitHub Actions CI**（PR 自動跑 ruff / mypy / pytest）
- [ ] release 自動 build wheel
- [ ] 受保護分支 + PR review 規則

---

## 第十層：使用者體驗（UX）

- [x] 斜線指令 + 自然語言雙軌
- [x] Markdown 即時渲染回覆
- [x] 自動置中 welcome、focus 橘框、spinner
- [x] SlashMenu / AtMenu 自動補全
- [x] ESC 中斷、輸入歷史持久化
- [x] 錯誤訊息可行動
- [ ] 操作員「一眼看懂車現在要幹嘛」的狀態總覽面板

---

## v1.0.0 出場條件（Definition of Done）

達成以下才視為「可上線」：

1. **安全層全綠**：E-stop、fail-safe、watchdog、速度夾限、危險動作確認、安全測試。
2. **可靠性**：車輛狀態機 + 動作完成回報 + 重連策略。
3. **可觀測性**：完整稽核軌跡 + 即時車輛狀態（位置 / 速度）。
4. **SIL 驗證**：Isaac Sim 跑通完整「自然語言 → 移動 → 到達回報」流程。
5. **Security**：控車指令存取控制 + 網路隔離。
6. **CI/CD**：PR 自動檢查 + 受保護分支。
7. **文件**：架構圖 + 操作員安全手冊 + 開發指南。

---

### 目前體檢結論（v0.3.3）

- **強項**：模塊化、可讀性、可測試性、錯誤降級、版本紀律、UX。
- **最大缺口**：**第一層安全（E-stop / watchdog / 速度夾限 / fail-safe）幾乎空白**——這是從「Demo / 工具」走向「可控實體車產品」最關鍵的一步。
- **建議下一步（v0.4 安全層）**：先做 ① 執行層速度夾限 + ② E-stop + ③ cmd_vel watchdog，這三項投報率最高、且能立即降低實車風險。
