FROM python:3.11-slim

WORKDIR /app

# Install uv for Python dependency management
RUN pip install uv

# Copy project files
COPY pyproject.toml .
COPY uv.lock .
COPY README.md .
COPY src/ src/
COPY chat-ui/dist/ chat-ui/dist/
COPY voice-agent-config.yaml .
COPY voice-mode.md .

# Install dependencies using uv
RUN uv sync --frozen

EXPOSE 8001

CMD ["uv", "run", "uvicorn", "src.voice_agent.main:app", "--host", "0.0.0.0", "--port", "8001"]
