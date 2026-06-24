from __future__ import annotations

from pathlib import Path

from ren_agent.core.files import (
    expand_at_mentions,
    list_project_files,
    read_file_snippet,
)


def _make_tree(root: Path) -> None:
    (root / "src").mkdir()
    (root / "src" / "main.py").write_text("print('hi')\n", encoding="utf-8")
    (root / "README.md").write_text("# title\n", encoding="utf-8")
    # 應被忽略的目錄與隱藏檔
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("x", encoding="utf-8")
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "x.pyc").write_text("x", encoding="utf-8")
    (root / ".secret").write_text("x", encoding="utf-8")


def test_list_project_files_applies_ignores(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    files = list_project_files(tmp_path)

    assert "src/main.py" in files
    assert "README.md" in files
    # 忽略目錄 / 隱藏目錄 / 隱藏檔不應出現
    assert not any(f.startswith(".git") for f in files)
    assert not any("__pycache__" in f for f in files)
    assert ".secret" not in files


def test_list_project_files_respects_limit(tmp_path: Path) -> None:
    for i in range(10):
        (tmp_path / f"f{i}.txt").write_text("x", encoding="utf-8")
    files = list_project_files(tmp_path, limit=3)
    assert len(files) == 3


def test_read_file_snippet_truncates(tmp_path: Path) -> None:
    p = tmp_path / "big.txt"
    p.write_text("A" * 50, encoding="utf-8")
    snippet = read_file_snippet(p, max_bytes=10)
    assert "截斷" in snippet
    assert snippet.startswith("A" * 10)


def test_expand_at_mentions_inlines_file(tmp_path: Path) -> None:
    (tmp_path / "note.txt").write_text("hello world", encoding="utf-8")
    message, used = expand_at_mentions("看一下 @note.txt 內容", root=tmp_path)

    assert used == ["note.txt"]
    assert "看一下 @note.txt 內容" in message
    assert "hello world" in message
    assert '<file path="note.txt">' in message


def test_expand_at_mentions_ignores_missing_and_traversal(tmp_path: Path) -> None:
    message, used = expand_at_mentions(
        "@nope.txt 還有 @../outside.txt", root=tmp_path
    )
    assert used == []
    assert message == "@nope.txt 還有 @../outside.txt"


def test_expand_at_mentions_no_at_returns_original(tmp_path: Path) -> None:
    message, used = expand_at_mentions("沒有提及任何檔案", root=tmp_path)
    assert used == []
    assert message == "沒有提及任何檔案"
