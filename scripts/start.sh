#!/bin/bash
cd "$(dirname "$0")/.."
uv run uvicorn voice_agent.main:app --host 0.0.0.0 --port 8000 --reload
