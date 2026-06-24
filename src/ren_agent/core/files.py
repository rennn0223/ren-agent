"""
專案檔案索引與 @ 檔案 mention 展開。

供 TUI 的 @ 補全選單與「送出時把 @path 換成檔案內容」使用。
"""
from __future__ import annotations

import os
import re
from pathlib import Path

# 索引時略過的目錄
IGNORE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    ".langgraph_api",
    ".idea",
    ".vscode",
}

# 單一檔案最多讀取的位元組數，避免把超大檔塞進 prompt
MAX_FILE_BYTES = 100_000

# 索引檔案數上限，避免在巨大專案中卡住
MAX_INDEX_FILES = 2000

_AT_RE = re.compile(r"@([^\s@]+)")


def list_project_files(root: str | Path | None = None, limit: int = MAX_INDEX_FILES) -> list[str]:
    """列出專案內的相對檔案路徑（套用 IGNORE_DIRS 與隱藏目錄過濾）。"""
    base = Path(root or Path.cwd())
    out: list[str] = []

    for dirpath, dirnames, filenames in os.walk(base):
        # 原地過濾要遞迴的子目錄：略過忽略清單與隱藏目錄
        dirnames[:] = [
            d for d in dirnames if d not in IGNORE_DIRS and not d.startswith(".")
        ]
        rel_dir = Path(dirpath).relative_to(base)
        for name in filenames:
            if name.startswith("."):
                continue
            rel = (rel_dir / name).as_posix()
            out.append(rel)
            if len(out) >= limit:
                return sorted(out)

    return sorted(out)


def read_file_snippet(path: str | Path, max_bytes: int = MAX_FILE_BYTES) -> str:
    """讀取檔案內容（最多 max_bytes），無法讀取時回傳錯誤說明字串。"""
    p = Path(path)
    try:
        data = p.read_bytes()
    except OSError as exc:
        return f"[無法讀取檔案：{exc}]"

    truncated = len(data) > max_bytes
    text = data[:max_bytes].decode("utf-8", errors="replace")
    if truncated:
        text += f"\n... [截斷，僅顯示前 {max_bytes} bytes]"
    return text


def expand_at_mentions(
    message: str, root: str | Path | None = None
) -> tuple[str, list[str]]:
    """
    把訊息中的 @path 換成附帶的檔案內容。

    回傳 (expanded_message, used_paths)。若沒有任何有效檔案，回傳原訊息與空清單。
    只接受 root 底下的真實檔案，避免路徑穿越。
    """
    base = Path(root or Path.cwd()).resolve()
    used: list[str] = []
    blocks: list[str] = []

    for match in _AT_RE.finditer(message):
        rel = match.group(1)
        candidate = (base / rel).resolve()

        # 安全檢查：必須落在 root 內，且為真實檔案
        if not str(candidate).startswith(str(base)):
            continue
        if not candidate.is_file():
            continue
        if rel in used:
            continue

        content = read_file_snippet(candidate)
        blocks.append(f'<file path="{rel}">\n{content}\n</file>')
        used.append(rel)

    if not blocks:
        return message, []

    expanded = message + "\n\n" + "\n\n".join(blocks)
    return expanded, used
