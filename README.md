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

***

## ✨ 功能特色

- 🤖 **本地 LLM**：透過 Ollama 串接，無需雲端、保護隱私（預設 `qwen3.6:35b`）
- 🖥️ **Claude Code 風 TUI**：圓角邊框、橘色 focus、spinner、自動置中 welcome panel
- 🚗 **車輛控制**：`/drive forward|back|left|right|stop` 直接發 `geometry_msgs/Twist` 到 `/cmd_vel`
- 📍 **座標導航**：`/goto 應科大樓` 從 `locations.yaml` 查 `{x, y}` JSON 發給 Isaac Sim
- 📡 **ROS2 整合（rclpy）**：單例 Node + executor，`/ros topics|echo|type|pub` 自動推斷訊息型別
- 🛠️ **Ollama Tool Calling**：LLM 看懂自然語言「往前走」「帶我去機械系館」自己呼叫工具
- 🔌 **Skills / Commands 架構**：TUI 只管 UI，能力邏輯拆到 registry 與 skills 模組
- 🚀 **一鍵啟動**：可透過 `renagent connect` 自動載入 ROS2 環境並開啟 TUI

***

## 📋 系統需求

| 需求 | 版本 |
|---|---|
| Python | 3.12+ |
| uv | 最新版 |
| Ollama | 最新版 |
| OS | Linux / macOS（推薦） |
| ROS2 | Humble/相容版本（若需 ROS2 功能） |

***

## 🚀 安裝步驟

### 1. 安裝 uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.cargo/env   # 或重新開啟 terminal
```

### 2. 安裝 Ollama 並拉取模型

```bash
curl -fsSL https://ollama.com/install.sh | sh

# 啟動 Ollama 服務
ollama serve &

# 拉取你想用的模型（擇一）
ollama pull qwen2.5:7b
ollama pull llama3.2
ollama pull qwen3:8b
```

### 3. Clone 專案

```bash
git clone https://github.com/rennn0223/ren-agent.git
cd ren-agent
```

### 4. 安裝專案依賴

```bash
uv sync --dev
```

uv 會自動建立 `.venv` 並安裝依賴，不需要手動 `pip install`。

### 5. 啟動 TUI

#### 方式 A：直接啟動

```bash
uv run python -m ren_agent.tui.main
```

#### 方式 B：用 CLI 啟動

```bash
uv run ren-agent tui
```

或指定模型與 Ollama 位址：

```bash
uv run ren-agent tui --model qwen3:8b --host http://localhost:11434
```

#### 方式 C：一鍵啟動（推薦）

先建立 `renagent` 啟動腳本並加入 PATH，之後可直接：

```bash
renagent connect
```

這個指令會：

- source ROS2 環境
- 進入 `ren-agent` 專案目錄
- 以 uv 啟動 TUI

***

## 🎮 使用方式

啟動後，直接在輸入框打字並按 `Enter` 即可與模型對話。

### 斜線指令

| 指令 | 功能 |
|---|---|
| `/help` | 顯示所有可用指令 |
| `/clear` | 清空對話記錄與 AI 歷史 |
| `/model <名稱>` | 切換模型，例如 `/model qwen3:8b` |
| `/ros topics` | 列出目前 ROS2 topics |
| `/ros echo <topic>` | 單次讀取指定 topic |
| `/ros type <topic>` | 顯示 topic 的訊息型別與欄位 |
| `/ros pub <topic> <json>` | 發布 JSON 到指定 topic（自動推斷型別） |
| `/drive forward\|back\|left\|right\|stop [speed] [duration]` | 控制車子，預設 0.3 m/s 跑 1 秒後自動 stop |
| `/goto <地名>` / `/goto list` | 從 `locations.yaml` 取座標送 JSON 給 Isaac Sim |
| `/bye` | 結束並關閉 ren-agent |

### 鍵盤快捷鍵

| 快捷鍵 | 功能 |
|---|---|
| `Enter` | 送出訊息 |
| `Tab` | 補全目前 Slash 指令 |
| `↑ / ↓` | SlashMenu 選取 / 輸入 history |
| `Ctrl+L` | 清空對話 |
| `Ctrl+N` | 新對話 |
| `Ctrl+C` | 強制離開 |

***

## 🛠️ 開發指令

```bash
# 程式碼檢查
uv run ruff check src tests

# 型別檢查
uv run mypy src

# 執行測試
uv run pytest -q

# 同時跑全部（建議每次 commit 前執行）
uv run ruff check src tests && uv run mypy src && uv run pytest -q
```

***

## 📁 專案結構

```text
ren-agent/
├── src/ren_agent/
│   ├── __main__.py              # CLI 入口（typer）
│   ├── core/
│   │   ├── commands.py          # Slash command registry
│   │   ├── config.py            # Pydantic 設定（含 ROS2 topic 名稱）
│   │   ├── logger.py            # Loguru 結構化日誌
│   │   ├── ollama_client.py     # Async Ollama 串流 + tool calling 迴圈
│   │   └── skills.py            # Skill registry（含 tool_schema）
│   ├── tools/
│   │   ├── ros2_node.py         # rclpy 單例 Node + executor thread
│   │   ├── ros2_skills.py       # topic list / echo / type / publish
│   │   ├── drive.py             # /drive：發 Twist 到 /cmd_vel
│   │   └── goto.py              # /goto：地名→JSON 給 Isaac Sim
│   ├── data/
│   │   └── locations.yaml       # 校園地點座標表
│   └── tui/
│       ├── app.py               # Textual TUI 主介面
│       └── main.py              # python -m 啟動入口
├── scripts/
│   └── renagent                 # 一鍵 connect 啟動腳本
├── tests/                       # commands / config / ollama agent
├── ROADMAP.md                   # 開發路線圖
├── CHANGELOG.md
├── README.md
└── pyproject.toml
```

***

## 🗺️ 開發路線圖

詳見 [ROADMAP.md](./ROADMAP.md)

| 版本 | 狀態 | 主要內容 |
|---|---|---|
| v0.1.0 | ✅ 完成 | TUI 基礎框架 + Ollama 對話 |
| v0.2.0 | ✅ 完成 | ROS2 topic 整合 + 錯誤提示 |
| v0.3.0 | ✅ 完成 | Skills / Commands 架構、一鍵啟動 |
| v0.3.1 | ✅ 完成 | rclpy 化、`/drive` `/goto`、Ollama tool calling、Claude Code 風 TUI |
| v0.4.0 | 📋 規劃中 | Isaac Sim 串接驗證、本地座標 frame、locations 編輯介面 |
| v0.5.0 | 📋 規劃中 | 多車協調、SLAM hook、安全/診斷 |

***

## 🤝 協作開發

目前建議以 `master` 為主線，功能先在 feature branch 開發，等 v0.3.0 穩定後再集中 compare / PR。

```text
feature/xxx  ->  master
```

建議流程：

1. 從 `master` 開 `feature/你的功能`
2. 在 feature branch 開發與自測
3. 功能成熟後再開 Pull Request → `master`
4. CI 通過後 merge
5. 達到里程碑時打 tag / release

***

## 📜 授權

MIT License — 詳見 [LICENSE](./LICENSE)

***

Made with ❤️ and a very long dachshund 🐾