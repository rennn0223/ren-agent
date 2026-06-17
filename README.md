# 🐾 ren-agent

> 車載專用 AI Agent — 基於 Ollama + Textual 的本地 TUI 智能助理

```
██████╗ ███████╗███╗   ██╗      █████╗  ██████╗ ███████╗███╗   ██╗████████╗
██╔══██╗██╔════╝████╗  ██║     ██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝
██████╔╝█████╗  ██╔██╗ ██║     ███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║
██╔══██╗██╔══╝  ██║╚██╗██║     ██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║
██║  ██║███████╗██║ ╚████║     ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║
╚═╝  ╚═╝╚══════╝╚═╝  ╚═══╝     ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝
```

---

## ✨ 功能特色

- 🤖 **本地 LLM**：透過 Ollama 串接，無需雲端、保護隱私
- 🖥️ **TUI 介面**：基於 Textual 的互動式終端界面
- 🚗 **車載場景**：系統提示針對導航、安全、診斷等車載情境設計
- 📡 **ROS2 整合**（開發中）：讀取車載 topic、控制導航模組
- ⚡ **斜線指令**：內建 `/help`、`/clear`、`/model`、`/bye`

---

## 📋 系統需求

| 需求 | 版本 |
|---|---|
| Python | 3.11+ |
| uv | 最新版 |
| Ollama | 最新版 |
| OS | Linux / macOS（推薦）|

---

## 🚀 安裝步驟

### 1. 安裝 uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.cargo/env   # 或重新開啟 terminal
```

### 2. 安裝 Ollama 並拉取模型

```bash
# 安裝 Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 啟動 Ollama 服務
ollama serve &

# 拉取你想用的模型（擇一）
ollama pull qwen2.5:7b        # 輕量版，適合一般硬體
ollama pull llama3.2          # Meta Llama 3.2
ollama pull qwen3:8b          # 推薦：效果與速度平衡佳
```

### 3. Clone 專案

```bash
git clone https://github.com/rennn223/ren-agent.git
cd ren-agent
```

### 4. 安裝專案依賴

```bash
uv sync --all-extras --dev
```

uv 會自動建立 `.venv` 並安裝所有依賴，不需要手動 `pip install`。

### 5. 啟動 TUI

```bash
uv run ren-agent tui
```

或指定模型與 Ollama 位址：

```bash
uv run ren-agent tui --model qwen3:8b --host http://localhost:11434
```

---

## 🎮 使用方式

啟動後，直接在輸入框打字並按 `Enter` 即可與模型對話。

### 斜線指令

| 指令 | 功能 |
|---|---|
| `/help` | 顯示所有可用指令 |
| `/clear` | 清空對話記錄與 AI 記憶 |
| `/model <名稱>` | 切換模型，例如 `/model llama3.2` |
| `/bye` | 結束並關閉 ren-agent |

### 鍵盤快捷鍵

| 快捷鍵 | 功能 |
|---|---|
| `Enter` | 送出訊息 |
| `Ctrl+L` | 清空對話 |
| `Ctrl+N` | 新對話 |
| `F1` | 收合 / 展開側欄 |
| `Ctrl+C` | 強制離開 |

---

## 🛠️ 開發指令

```bash
# 程式碼檢查
uv run ruff check src/ tests

# 型別檢查
uv run mypy src

# 執行測試
uv run pytest -q

# 同時跑全部（建議每次 commit 前執行）
uv run ruff check src/ tests && uv run mypy src && uv run pytest -q
```

---

## 📁 專案結構

```
ren-agent/
├── src/ren_agent/
│   ├── __main__.py          # CLI 入口（typer）
│   ├── core/
│   │   ├── config.py        # Pydantic 設定 + YAML 持久化
│   │   ├── logger.py        # Loguru 結構化日誌
│   │   └── ollama_client.py # Async Ollama 串流客戶端
│   ├── tui/
│   │   └── app.py           # Textual TUI 主介面
│   └── tools/
│       └── ros2_stub.py     # ROS2 工具 stub（v0.2 實作）
├── tests/                   # 單元測試（v0.3 補完）
├── .github/workflows/
│   ├── ci.yml               # PR 自動 lint + test
│   └── release.yml          # push tag → 自動發版
├── ROADMAP.md               # 開發路線圖
├── CHANGELOG.md             # 版本紀錄
└── pyproject.toml           # uv 專案設定
```

---

## 🗺️ 開發路線圖

詳見 [ROADMAP.md](./ROADMAP.md)

| 版本 | 狀態 | 主要內容 |
|---|---|---|
| v0.1.0 | ✅ 完成 | TUI 基礎框架 + Ollama 對話 |
| v0.2.0 | 🔨 開發中 | ROS2 topic 整合 |
| v0.3.0 | 📋 規劃中 | 指令系統擴充 + 測試覆蓋 |
| v0.4.0 | 📋 規劃中 | 車載場景雛形 |
| v0.5.0 | 📋 規劃中 | Dashboard + Plugin 平台 |

---

## 🤝 協作開發

這個專案使用 GitHub Flow 進行協作：

1. 從 `develop` 分支建立 `feature/你的功能` 分支
2. 開發完成後開 Pull Request → `develop`
3. 互相 Code Review（至少 1 人 approve）
4. CI 通過後 merge
5. 達到里程碑時，PR → `master` 並打 tag

---

## 📜 授權

MIT License — 詳見 [LICENSE](./LICENSE)

---


Made with ❤️ and a very long dachshund 🐾

