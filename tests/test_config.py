from __future__ import annotations

from pathlib import Path

import ren_agent.core.config as config_mod
from ren_agent.core.config import AppConfig, get_config


def _reset_cache() -> None:
    config_mod._cached = None


def test_get_config_returns_defaults_when_missing(tmp_path, monkeypatch) -> None:
    fake_path = tmp_path / "config.yaml"
    monkeypatch.setattr("ren_agent.core.config.DEFAULT_CONFIG_PATH", fake_path)
    _reset_cache()

    config = get_config()

    assert config.ollama.host == "http://localhost:11434"
    assert config.ollama.model == "qwen3.6:35b"
    assert config.agent.name == "ren-agent"
    assert config.ros2.cmd_vel_topic == "/cmd_vel"
    assert config.ros2.goal_topic == "/ren_agent/goal"
    _reset_cache()


def test_save_and_load_yaml_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"

    cfg = AppConfig()
    cfg.ollama.host = "http://127.0.0.1:11434"
    cfg.ollama.model = "qwen3:8b"
    cfg.ros2.goal_topic = "/sim/goal"
    cfg.save_yaml(path)

    loaded = AppConfig.from_yaml(path)

    assert loaded.ollama.host == "http://127.0.0.1:11434"
    assert loaded.ollama.model == "qwen3:8b"
    assert loaded.ros2.goal_topic == "/sim/goal"


def test_from_yaml_handles_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "empty.yaml"
    path.write_text("", encoding="utf-8")

    cfg = AppConfig.from_yaml(path)
    assert cfg.ollama.model == "qwen3.6:35b"
    assert cfg.agent.name == "ren-agent"
