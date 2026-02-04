#!/bin/bash
cd "$(dirname "$0")/.."

# Cleanup function to kill background processes
cleanup() {
    echo "Shutting down..."
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
    exit 0
}
trap cleanup SIGINT SIGTERM

# Start backend
uv run uvicorn voice_agent.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# Start chat UI on port 3000
cd chat-ui
npm run dev -- --port 3000 &
FRONTEND_PID=$!

echo "Backend: http://localhost:8000"
echo "Chat UI: http://localhost:3000"

# Wait for both processes
wait
