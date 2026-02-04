"""Thin proxy for Pi deployment - forwards requests to PC.

Serves conversation history locally from synced folder.
Proxies write operations (chat, voice) to PC.
"""

import asyncio
import json
import logging
import os
import re
import subprocess
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Configuration from environment
PC_HOST = os.getenv("PC_HOST", "100.108.111.65")
PC_PORT = os.getenv("PC_PORT", "8000")
PC_MAC = os.getenv("PC_MAC", "d8:43:ae:f9:9f:36")
PC_BASE_URL = f"http://{PC_HOST}:{PC_PORT}"

# Local conversations directory (synced from PC via Syncthing)
CONVERSATIONS_DIR = Path(os.getenv("CONVERSATIONS_DIR", "/home/kevin/voice-agent/conversations"))

# Timeouts
HEALTH_TIMEOUT = 5.0
WOL_WAIT_TIMEOUT = 30.0
REQUEST_TIMEOUT = 90.0

app = FastAPI(title="Voice Agent Proxy")


async def check_pc_health() -> bool:
    """Check if PC is reachable."""
    try:
        async with httpx.AsyncClient(timeout=HEALTH_TIMEOUT) as client:
            resp = await client.get(f"{PC_BASE_URL}/health")
            return resp.status_code == 200
    except Exception:
        return False


async def wake_pc() -> bool:
    """Send WoL packet and wait for PC to come online."""
    logger.info(f"Sending WoL to {PC_MAC}...")
    subprocess.run(["wakeonlan", PC_MAC], check=False)

    # Poll for PC to come online
    for i in range(int(WOL_WAIT_TIMEOUT / 2)):
        await asyncio.sleep(2)
        if await check_pc_health():
            logger.info(f"PC online after {(i+1)*2}s")
            return True
        logger.info(f"Waiting for PC... ({(i+1)*2}s)")

    logger.error("PC did not come online within timeout")
    return False


async def ensure_pc_available() -> None:
    """Ensure PC is available, waking if necessary."""
    if await check_pc_health():
        return

    if not await wake_pc():
        raise HTTPException(status_code=503, detail="PC unavailable - wake failed")


async def simple_proxy(request: Request, path: str) -> Response:
    """Forward request to PC and return complete response (non-streaming)."""
    await ensure_pc_available()

    url = f"{PC_BASE_URL}/{path}"
    try:
        body = await request.body()
        logger.info(f"Proxy read {len(body)} bytes from client for {path}")
    except Exception as e:
        logger.error(f"Failed to read request body: {type(e).__name__}: {e}")
        raise

    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in ("host", "content-length")
    }

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        logger.info(f"Forwarding to {url}")
        resp = await client.request(
            request.method,
            url,
            headers=headers,
            content=body if body else None,
        )
        logger.info(f"PC responded: {resp.status_code}, {len(resp.content)} bytes")
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            media_type=resp.headers.get("content-type"),
        )


async def streaming_proxy(request: Request, path: str) -> StreamingResponse:
    """Forward request to PC and stream response back (for SSE)."""
    await ensure_pc_available()

    url = f"{PC_BASE_URL}/{path}"
    body = await request.body()
    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in ("host", "content-length")
    }

    client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT)

    async def stream_response():
        try:
            async with client.stream(
                request.method,
                url,
                headers=headers,
                content=body if body else None,
            ) as resp:
                async for chunk in resp.aiter_bytes():
                    yield chunk
        finally:
            await client.aclose()

    return StreamingResponse(
        stream_response(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


# API proxy routes - most use simple proxy
@app.get("/api/agents")
async def proxy_agents(request: Request):
    """Proxy agents list."""
    return await simple_proxy(request, "api/agents")


@app.post("/api/agents/switch")
async def proxy_agents_switch(request: Request):
    """Proxy agent switch."""
    return await simple_proxy(request, "api/agents/switch")


def get_preview_from_markdown(md_file: Path, max_length: int = 100) -> str:
    """Extract last user message from markdown conversation log."""
    if not md_file.exists():
        return ""
    try:
        content = md_file.read_text()
        # Find all user messages: **Kevin:** ...
        matches = re.findall(r"\*\*Kevin:\*\* (.+?)(?:\n\n|\n\*\*|$)", content, re.DOTALL)
        if matches:
            return matches[-1].strip()[:max_length]
    except OSError:
        pass
    return ""


def parse_markdown_conversation(md_file: Path) -> list[dict]:
    """Parse markdown conversation log into messages."""
    messages = []
    if not md_file.exists():
        return messages

    try:
        content = md_file.read_text()
        # Split by ## timestamp headers
        sections = re.split(r"^## \d{1,2}:\d{2}", content, flags=re.MULTILINE)

        for section in sections:
            if not section.strip():
                continue

            # Extract user message
            user_match = re.search(r"\*\*Kevin:\*\* (.+?)(?:\n\n|\n\*\*|$)", section, re.DOTALL)
            if user_match:
                messages.append({"role": "user", "content": user_match.group(1).strip()})

            # Extract agent response
            agent_match = re.search(r"\*\*Agent:\*\* (.+?)(?:\n\n|\n\*\*|$)", section, re.DOTALL)
            if agent_match:
                messages.append({"role": "assistant", "content": agent_match.group(1).strip()})
    except OSError:
        pass

    return messages


@app.get("/api/conversations")
async def get_conversations():
    """Serve conversations list from local synced folder."""
    conversations = []

    if not CONVERSATIONS_DIR.exists():
        logger.warning(f"Conversations directory not found: {CONVERSATIONS_DIR}")
        return JSONResponse(content=[])

    # Scan all agent subdirectories
    for agent_dir in CONVERSATIONS_DIR.iterdir():
        if not agent_dir.is_dir() or agent_dir.name.startswith('.'):
            continue

        agent_name = agent_dir.name

        # Look for markdown conversation files (YYYY-MM-DD.md pattern)
        for md_file in agent_dir.glob("????-??-??.md"):
            date = md_file.stem  # e.g., "2026-01-31"
            preview = get_preview_from_markdown(md_file)

            # Check for session file with Claude conversation ID
            conversation_id = date
            session_file = agent_dir / ".claude-session.json"
            if session_file.exists():
                try:
                    data = json.loads(session_file.read_text())
                    if data.get("date") == date:
                        conversation_id = data.get("conversation_id", date)
                except (json.JSONDecodeError, OSError):
                    pass

            conversations.append({
                "id": conversation_id,
                "date": date,
                "preview": preview,
                "agent": agent_name,
            })

    # Sort by date descending
    conversations.sort(key=lambda x: x["date"], reverse=True)
    return JSONResponse(content=conversations)


@app.get("/api/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    """Serve conversation from local markdown files.

    Falls back to proxying to PC if local data unavailable.
    """
    # Search for the conversation in all agent directories
    if CONVERSATIONS_DIR.exists():
        for agent_dir in CONVERSATIONS_DIR.iterdir():
            if not agent_dir.is_dir():
                continue

            # Find session file with matching conversation ID
            for session_file in agent_dir.glob("*.claude-session.json"):
                try:
                    data = json.loads(session_file.read_text())
                    if data.get("conversation_id") == conversation_id:
                        date = data.get("date")
                        if date:
                            md_file = agent_dir / f"{date}.md"
                            messages = parse_markdown_conversation(md_file)
                            if messages:
                                return JSONResponse(content={
                                    "id": conversation_id,
                                    "messages": messages,
                                })
                except (json.JSONDecodeError, OSError):
                    continue

    # Fallback: try proxying to PC
    logger.info(f"Conversation {conversation_id} not found locally, proxying to PC")
    try:
        if await check_pc_health():
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                resp = await client.get(f"{PC_BASE_URL}/api/conversations/{conversation_id}")
                return Response(
                    content=resp.content,
                    status_code=resp.status_code,
                    media_type=resp.headers.get("content-type"),
                )
    except Exception as e:
        logger.warning(f"Failed to proxy conversation request: {e}")

    raise HTTPException(status_code=404, detail="Conversation not found")


# Chat uses streaming for SSE
@app.post("/api/chat")
async def proxy_chat(request: Request):
    """Proxy chat endpoint with SSE streaming."""
    return await streaming_proxy(request, "api/chat")


# Voice endpoints use simple proxy (binary data, not streaming)
@app.post("/voice")
async def proxy_voice(request: Request):
    """Proxy voice endpoint."""
    try:
        content_length = request.headers.get("content-length", "unknown")
        logger.info(f"Voice request received, content-length: {content_length}")
        result = await simple_proxy(request, "voice")
        logger.info(f"Voice request completed, response size: {len(result.body) if result.body else 0}")
        return result
    except Exception as e:
        logger.error(f"Voice proxy error: {type(e).__name__}: {e}")
        return JSONResponse(
            status_code=502,
            content={"error": str(e), "type": type(e).__name__}
        )


@app.post("/transcribe")
async def proxy_transcribe(request: Request):
    """Proxy transcribe endpoint."""
    return await simple_proxy(request, "transcribe")


@app.post("/tts")
async def proxy_tts(request: Request):
    """Proxy TTS endpoint."""
    return await simple_proxy(request, "tts")


@app.get("/health")
async def health():
    """Proxy health check."""
    pc_healthy = await check_pc_health()
    return {"status": "ok", "pc_available": pc_healthy}


# Static file serving for chat UI
CHAT_UI_DIR = Path(__file__).parent.parent.parent / "chat-ui" / "dist"

if CHAT_UI_DIR.exists():
    app.mount("/assets", StaticFiles(directory=CHAT_UI_DIR / "assets"), name="assets")

    @app.get("/{path:path}")
    async def serve_spa(path: str = "") -> FileResponse:
        """Serve React SPA for all non-API routes."""
        return FileResponse(CHAT_UI_DIR / "index.html")
