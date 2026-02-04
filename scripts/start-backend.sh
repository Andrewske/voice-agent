#!/bin/bash
# Start backend only (for use with Pi proxy)
cd "$(dirname "$0")/.."
exec uv run uvicorn src.voice_agent.main:app --host 0.0.0.0 --port 8000
