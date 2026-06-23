# ren-agent ROADMAP 稽核報告

> 稽核日期：2026-06-18  
> 對照檔案：`ROADMAP.md`  
> 專案版本：`pyproject.toml` 標示 **0.2.0**（與 v0.3.0 勾選進度不一致）  
> 目前分支：`feature/v0.3.0-core`（`master` 亦存在）

本文件供其他 AI / 協作者快速了解：**ROADMAP 上已打勾的項目是否真的有做完**、哪些描述過時、下一步建議。

---

## 執行摘要

| 類別 | 數量 | 說明 |
|------|------|------|
| ✅ 已完成（勾選正確） | ~28 項 | 程式碼與 ROADMAP 一致 |
| ⚠️ 部分完成 / 描述過時 | 4 項 | 建議修正 ROADMAP 文字或降勾 |
| ⬜ 未勾選且確實未完成 | 多項 | ROADMAP 標示正確 |
| ❌ 誤勾（應取消） | 0 項 | 無完全沒做卻勾選的項目 |

**結論：** ROADMAP 整體可信，但 ROS2 實作路徑、ASCII banner、Tool/Skill 命名、版本號需要同步更新。

---

## 專案現況速覽

### 目錄結構（核心）

```
src/ren_agent/
├── __main__.py              # CLI 入口 (ren-agent tui)
├── core/
│   ├── commands.py          # Slash command registry + handlers
│   ├── skills.py            # Skill 註冊與執行
│   ├── config.py            # Pydantic 設定
│   └── ollama_client.py     # Ollama 非同步串流
├── tui/
│   ├── app.py               # Textual 主介面（~919 行）
│   └── main.py              # python -m ren_agent.tui.main
└── tools/
    ├── ros2_skills.py       # ROS2 skills（**TUI 實際使用**）
    └── ros2_stub.py         # ROS2 subprocess（**已無引用，遺留檔**）

tests/
└── test_commands.py         # registry / /q 指令測試（2 passed）

scripts/
└── renagent                 # renagent connect / tui 一鍵啟動
```

### 啟動方式（已實作）

```bash
uv run python -m ren_agent.tui.main
uv run ren-agent tui
./scripts/renagent connect   # source ROS2 + 啟動 TUI
```

### 測試現況

```bash
uv run pytest -q    # 2 passed（僅 test_commands.py）
uv run ruff check src tests
uv run mypy src     # README 有說明，pyproject 有 dev 依賴
```

---

## v0.1.0 — 基礎 TUI + Ollama Chat

| ROADMAP 項目 | 勾選 | 稽核結果 | 證據 / 備註 |
|--------------|------|----------|-------------|
| 使用 Textual 建立 TUI 主架構 | [x] | ✅ 完成 | `tui/app.py` |
| 整合 Ollama Python Client | [x] | ✅ 完成 | `core/ollama_client.py` |
| 實作非同步串流回應 | [x] | ✅ 完成 | `chat_stream()` + `stream_response()` |
| 設計 REN AGENT ASCII banner | [x] | ⚠️ 部分 | README 有大 ASCII；TUI 已改為 `HeroCard` 邊框標題 + 臘腸狗 |
| 加入臘腸狗吉祥物 | [x] | ✅ 完成 | `MascotArt` in `app.py` |
| 斜線指令 `/help` `/clear` `/model` `/bye` | [x] | ✅ 完成 | `core/commands.py` |
| 設定 Ruff / mypy / pytest + uv | [x] | ✅ 完成 | `pyproject.toml` + README |
| 第一個穩定版 commit & push (master) | [x] | ✅ 完成 | `master` 分支存在，有 `3cda517` 等 commit |

---

## v0.2.0 — ROS2 整合與車載基礎能力

| ROADMAP 項目 | 勾選 | 稽核結果 | 證據 / 備註 |
|--------------|------|----------|-------------|
| `/ros topics` 列出 topic | [x] | ✅ 完成 | `handle_slash_command` → `ros-topics` skill |
| `/ros echo <topic>` 單次讀取 | [x] | ✅ 完成 | `ros-echo` skill |
| 將 `tools/ros2_stub.py` 實作為真實 ROS2 工具 | [x] | ⚠️ 路徑已變 | `ros2_stub.py` 有 subprocess，但 **TUI 已改用 `ros2_skills.py`**，`ros2_stub` 無引用 |
| 使用 subprocess 呼叫 `ros2` CLI | [x] | ✅ 完成 | 實際在 `ros2_skills.py` |
| 輸出格式化顯示在 chat-log | [x] | ✅ 完成 | `_CommandCtx.run_skill` → `write_system()` |
| 導入「駕駛場景系統提示」 | [ ] | ⬜ 未完成 | `config.py` 僅單一 `system_prompt`，無 profile 切換 |
| system prompt 可切換 profile | [ ] | ⬜ 未完成 | — |
| WebUI 狀態面板 | [ ] | ⬜ 未完成 | — |
| Ollama 連線失敗友善錯誤 | [x] | ✅ 完成 | 狀態列 `✗ Ollama 未啟動 — 請執行: ollama serve` |
| ROS2 指令失敗顯示原因 | [x] | ✅ 完成 | skill 回傳錯誤字串 |

---

## v0.3.0 — 開發體驗與擴充性

| ROADMAP 項目 | 勾選 | 稽核結果 | 證據 / 備註 |
|--------------|------|----------|-------------|
| Slash commands registry | [x] | ✅ 完成 | `core/commands.py`：`register_command`, `get_command`, `all_commands` |
| 自訂 alias（如 `/nav` = `/profile navigation`） | [ ] | ⬜ 未完成 | 正確未勾；僅內建 alias：`exit`/`quit`, `ask`, `ros2` |
| 設計 Skills 模組介面 | [x] | ✅ 完成 | `core/skills.py` |
| 定義 `Tool` / `Skill` 介面 | [x] | ⚠️ 命名過寬 | 僅有 `Skill`，**無獨立 `Tool` 類別** |
| ROS2 邏輯搬進獨立模組 | [x] | ✅ 完成 | `tools/ros2_skills.py` |
| TUI 只負責 UI | [x] | ✅ 完成 | `CommandContext` + registry 分離 |
| 輸入 history 快捷鍵 | [x] | ✅ 完成 | `↑/↓` → `_input_history`（SlashMenu 關閉時） |
| 狀態列顯示最後回應時間 / 模型 | [x] | ✅ 完成 | `_last_response_at` + model 名 |
| SlashMenu 上下鍵 + Tab 補全 | [x] | ✅ 完成 | `SlashMenu` + bindings |
| 回合制排隊對話 | [x] | ✅ 完成 | `_pending_queue`, `_drain_queue()`, `_enqueue()` |
| `python -m ren_agent.tui.main` | [x] | ✅ 完成 | `tui/main.py` |
| `renagent connect` 啟動腳本 | [x] | ✅ 完成 | `scripts/renagent` |
| 基礎單元測試（父項） | [ ] | ⬜ 未完成 | 正確未勾 |
| config 載入 / 儲存測試 | [ ] | ⬜ 未完成 | — |
| OllamaAgent mock 測試 | [ ] | ⬜ 未完成 | — |
| slash command / registry 測試 | [x] | ✅ 完成 | `tests/test_commands.py`（2 tests） |
| README / 文件整理（父項） | [ ] | ⬜ 未完成 | README 已有啟動與架構說明，但缺最新截圖 |
| README 最新啟動方式與架構 | [ ] | ⚠️ 部分 | README 已寫，但 ROADMAP 父項仍未勾 |
| TUI 截圖 | [ ] | ⬜ 未完成 | — |

---

## v0.4.0+ / 維運（未勾選項）

以下 ROADMAP **未勾選**，稽核確認**確實尚未實作**：

- v0.4.0：導航 `/nav`、安全 `/safety check`、車載 system prompt 強化
- v0.5.0：MCP/plugin 平台、WebUI / Dashboard、FastAPI skeleton
- CI：GitHub Actions（ruff / mypy / pytest）
- `CONTRIBUTING.md`、`CHANGELOG.md`、發版策略

唯一已勾選的維運項：

| 項目 | 勾選 | 稽核結果 |
|------|------|----------|
| 在 `ROADMAP.md` 持續更新進度 | [x] | ✅ `ROADMAP.md` 存在且持續維護 |

---

## 已知落差與建議修正

### 1. 版本號不一致

- `pyproject.toml`：`version = "0.2.0"`
- `ROADMAP.md`：v0.3.0 多項已勾選
- **建議：** bump 至 `0.3.0`，或將未完成項目的勾選收回

### 2. ROS2 雙模組遺留

| 檔案 | 狀態 |
|------|------|
| `tools/ros2_skills.py` | ✅ TUI 實際使用 |
| `tools/ros2_stub.py` | ⚠️ 有實作但無引用 |

**建議：** ROADMAP 改寫為「ROS2 skills 模組」；刪除或合併 `ros2_stub.py`

### 3. ROADMAP 文字建議更新

| 現有描述 | 建議改為 |
|----------|----------|
| 設計 REN AGENT ASCII banner | TUI HeroCard 歡迎區（邊框標題 + 臘腸狗）；README 保留 ASCII |
| 將 `ros2_stub.py` 實作為真實 ROS2 工具 | `ros2_skills.py` 透過 subprocess 整合 ROS2 |
| 定義 `Tool` / `Skill` 介面 | 定義 `Skill` 介面（`core/skills.py`） |

### 4. 測試覆蓋率偏低

目前僅 `tests/test_commands.py`（2 tests）。ROADMAP 父項「撰寫基礎單元測試」正確標為未完成。

---

## TUI 對話邏輯（供其他 AI 接續開發）

目前 `app.py` 採 **Claude / Codex 風格回合制**：

1. **忙碌時送出**：只進 `_pending_queue`，狀態列顯示佇列，**不提前寫入 transcript**
2. **輪到處理時**：`write_user(message)` → `begin_agent_stream()` → 串流回覆
3. **Slash command**：走 `core/commands.py` registry，不與一般對話混用（`/bye` 可立即執行）
4. **排隊項目**：`("message", text)` 或 `("slash", "/help")`
5. **完成後**：`_work_finished()` → `_drain_queue()` 處理下一則

相關符號：

- 使用者回合：`› message`（深灰底白字）
- 系統訊息：`write_system()` → 灰色 dim
- 助手串流：純文字，無 Q:/A: 前綴（有 `_sanitize_llm_output` 過濾模型多餘 Q/A 包裝）

---

## 給接手的 AI：優先待辦（依 ROADMAP 未勾選項）

1. **駕駛場景 system prompt profile**（導航 / 安全 / 診斷）
2. **config / OllamaAgent 單元測試**
3. **README 截圖 + CHANGELOG**
4. **GitHub Actions CI**
5. **清理 `ros2_stub.py` 或合併進 skills**
6. **版本號同步為 0.3.0**
7. v0.4.0：`/nav`、`/safety check` mock 服務

---

## Git 參考（稽核時）

```
675045d feat(core): slash command registry + skills + TUI history
b8198e6 Merge pull request #1 from rennn0223/feature/ros2-topic-tools
f2981c7 feat(tui): v0.2.0 final — streaming, queue, slash menu, ROS2 subprocess
8c8bc61 docs: add README and roadmap for ren-agent v0.1.0
3cda517 feat: initialize ren-agent v0.1.0 TUI (Textual + Ollama + dachshund mascot)
```

分支：`master`、`feature/ros2-topic-tools`、`feature/v0.3.0-core`（目前工作分支）

---

*本文件由程式碼靜態稽核產生，未執行完整 E2E（Ollama / ROS2 實機連線）。*
