from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from ren_agent.core.config import OllamaConfig
from ren_agent.core.ollama_client import OllamaAgent


def test_set_system_prompt_and_reset_history() -> None:
    async def _run() -> None:
        agent = OllamaAgent(OllamaConfig())
        agent.set_system_prompt("system prompt a")

        assert agent.history[0]["role"] == "system"
        assert agent.history[0]["content"] == "system prompt a"

        agent.history.append({"role": "user", "content": "hello"})
        agent.history.append({"role": "assistant", "content": "world"})
        agent.reset_history()

        assert len(agent.history) == 1
        assert agent.history[0]["role"] == "system"

    asyncio.run(_run())


def test_chat_stream_yields_tokens_and_saves_history() -> None:
    async def _run() -> None:
        agent = OllamaAgent(OllamaConfig(model="qwen3:8b"))

        chunk1 = type("Chunk", (), {})()
        chunk1.message = type("Msg", (), {"content": "Hello"})()

        chunk2 = type("Chunk", (), {})()
        chunk2.message = type("Msg", (), {"content": " world"})()

        async def fake_chat(*args, **kwargs):
            async def agen():
                yield chunk1
                yield chunk2
            return agen()

        fake_client = AsyncMock()
        fake_client.chat = fake_chat

        with patch("ren_agent.core.ollama_client.AsyncClient", return_value=fake_client):
            tokens = []
            async for token in agent.chat_stream("hi"):
                tokens.append(token)

        assert tokens == ["Hello", " world"]
        assert agent.history[-1]["role"] == "assistant"
        assert agent.history[-1]["content"] == "Hello world"

    asyncio.run(_run())


def test_check_connection_success() -> None:
    async def _run() -> None:
        agent = OllamaAgent(OllamaConfig())

        fake_models = type("Models", (), {})()
        fake_models.models = [type("M", (), {"model": "qwen3:8b"})()]

        fake_client = AsyncMock()
        fake_client.list = AsyncMock(return_value=fake_models)

        with patch("ren_agent.core.ollama_client.AsyncClient", return_value=fake_client):
            ok = await agent.check_connection()

        assert ok is True

    asyncio.run(_run())