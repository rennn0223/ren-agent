from __future__ import annotations

from pathlib import Path

from ren_agent.core.config import AppConfig, DEFAULT_CONFIG_PATH, get_config


def test_get_config_returns_defaults_when_missing(tmp_path, monkeypatch) -> None:
    fake_path = tmp_path / "config.yaml"
    monkeypatch.setattr("ren_agent.core.config.DEFAULT_CONFIG_PATH", fake_path)

    config = get_config()

    assert config.ollama.host == "http://localhost:11434"
    assert config.ollama.model == "qwen3.6:35b"
    assert config.agent.name == "ren-agent"
    assert config.agent.version == "0.3.0"


def test_save_and_load_yaml_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"

    config = AppConfig()
    config.ollama.host = "http://127.0.0.1:11434"
    config.ollama.model = "qwen3:8b"
    config.agent.version = "0.3.0"
    config.save_yaml(path)

    loaded = AppConfig.from_yaml(path)

    assert loaded.ollama.host == "http://127.0.0.1:11434"
    assert loaded.ollama.model == "qwen3:8b"
    assert loaded.agent.version == "0.3.0"


def test_from_yaml_handles_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "empty.yaml"
    path.write_text("", encoding="utf-8")

    config = AppConfig.from_yaml(path)

    assert config.ollama.model == "qwen3.6:35b"
    assert config.agent.name == "ren-agent"