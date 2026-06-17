# ren-agent

A minimal LangGraph agent powered by Ollama, with LangSmith tracing support.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- [Ollama](https://ollama.com/)

## Setup

1) Install dependencies

```bash
uv sync
```

2) Activate the virtual environment

```bash
. .venv/bin/activate
```

3) Start Ollama and pull the model

```bash
ollama serve
ollama pull qwen3.6:35b
```

4) Configure environment variables

```bash
cp .env.example .env
```

Set `LANGSMITH_API_KEY` in `.env` if you want tracing.

## Run the demo

```bash
python main.py
```

Expected output (example):

```text
It's 60 degrees and foggy.
```

## Run with LangGraph CLI

```bash
langgraph dev
```

The graph is configured in `langgraph.json`:

- Python version: `3.12`
- Graph entrypoint: `main.py:app`
- Environment file: `.env`

## Notes

- The `search` tool is a mock tool for demonstration and returns hard-coded weather responses.
- Change model by setting `OLLAMA_MODEL` in `.env` (default: `qwen3.6:35b`).

