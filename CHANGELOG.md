# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- v0.3.0 收尾：ROS2 CLI adapter 測試補齊。
- pytest 設定整理，預設關閉外部 plugin autoload。
- README / ROADMAP 文件整理。

### Fixed
- 修正 config YAML 讀寫的空值處理。
- 將 AgentConfig.version 對齊專案版本。

## [0.3.0] - 2026-06-23

### Added
- Slash commands registry。
- Skills registry。
- ROS2 CLI skills。
- `renagent connect` 一鍵啟動。
- 基礎測試覆蓋。
- README 更新為最新啟動方式與專案架構。

### Changed
- ROS2 相關實作改為獨立 skills 模組。
- TUI 由單一 chat app 擴充為 commands / skills 分層架構。