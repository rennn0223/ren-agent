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
- [x] 將 ROS2 工具整合為獨立模組
  - [x] 使用 subprocess 呼叫 `ros2` CLI
  - [x] 把輸出格式化後顯示在 chat-log
- [ ] 導入「駕駛場景系統提示」
  - [ ] 將 system prompt 抽成可切換 profile（導航 / 安全 / 診斷）
  - [ ] 在 WebUI 顯示當前 profile / ROS2 / recent activity 狀態面板
- [x] 增加簡單錯誤提示
  - [x] Ollama 連線失敗時顯示友善錯誤訊息
  - [x] ROS2 指令失敗時顯示原因

***

## 🔁 v0.3.0 — 開發體驗與擴充性

- [x] Slash commands 擴充機制
  - [x] 建立 `/` 指令註冊表（registry）
  - [ ] 支援自訂 alias，例如 `/nav` = `/profile navigation`
- [x] 設計 Skills 模組介面
  - [x] 定義 `Tool` / `Skill` 介面
  - [x] 把 ROS2 相關邏輯搬進獨立模組，讓 TUI 只負責 UI
- [x] TUI 體驗小改
  - [x] 支援輸入 history 快捷鍵
  - [x] 在狀態列顯示最後回應時間 / 模型名稱
  - [x] 支援 SlashMenu 上下鍵選取 + Tab 補全
  - [x] 支援回合制排隊對話
- [x] 一鍵啟動流程
  - [x] `python -m ren_agent.tui.main` 啟動入口
  - [x] `renagent connect` 啟動腳本
- [x] 撰寫基礎單元測試
  - [x] config 載入 / 儲存
  - [ ] OllamaAgent 基本對話（mock）
  - [x] slash command handler / commands/skills registry 行為測試
- [ ] README / 文件整理
  - [ ] README 加入最新啟動方式與架構說明
  - [ ] 補一張最新 TUI 截圖

***

## 🚗 v0.4.0 — 車載 Agent 功能雛形

- [ ] 導航能力（先以 mock API 模擬）
  - [ ] `/nav to <地點>`：回傳規劃路線文字摘要
  - [ ] 抽象出 NavigationService，未來能接真實導航 API
- [ ] 安全提醒 / 車況診斷（先以腳本模擬）
  - [ ] `/safety check`：回傳一組模擬車況檢查清單
  - [ ] 為之後連接真正車載 CAN / OBD 留接口
- [ ] 將「車載情境」寫入 system prompt，讓模型回答更貼近車內助手角色

***

## 🌐 v0.5.0 — Dashboard & 擴充平台雛形

- [ ] 設計「ren-agent MCP / plugin 平台」雛形
  - [ ] 在專案內定義簡單的 plugin discovery 規則（例如 `plugins/` 目錄）
  - [ ] 支援在設定檔打開 / 關閉 plugins
- [ ] 規劃 WebUI / Dashboard 版本
  - [ ] 定義 Textual app 與未來 WebUI 共用的核心邏輯層
  - [ ] 預留 HTTP API 介面（例如 FastAPI skeleton）
  - [ ] 將 sidebar / profile / ROS2 status / recent activity 轉到 WebUI

***

## 📦 維運與品質（持續進行）

- [ ] CI：GitHub Actions
  - [ ] PR 時自動執行 ruff / mypy / pytest
  - [ ] push tag `v*.*.*` 時自動 build 並建立 GitHub Release
- [ ] 文件
  - [x] 在 `ROADMAP.md` 持續更新進度與勾選狀態
  - [ ] README 更新架構圖 & demo 截圖
  - [ ] 新增 `CONTRIBUTING.md`
  - [ ] 新增 `CHANGELOG.md`
- [ ] 發版策略
  - [ ] v0.x 專注在功能與架構打底
  - [ ] v1.0.0 代表：ROS2 整合穩定 + 至少一個導航 / 安全實戰場景可用