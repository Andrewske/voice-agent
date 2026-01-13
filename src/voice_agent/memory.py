"""Mem0 memory integration for voice agent using REST API."""

import logging
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime
from typing import Any

import httpx
from dotenv import load_dotenv

# Load .env file
load_dotenv()

logger = logging.getLogger(__name__)

MEM0_API_BASE = "https://api.mem0.ai/v1"


def _get_headers() -> dict[str, str] | None:
    """Get API headers if key is configured."""
    api_key = os.environ.get("MEM0_API_KEY")
    if not api_key:
        return None
    return {
        "Authorization": f"Token {api_key}",
        "Content-Type": "application/json",
    }


def _search_memories(
    query: str,
    user_id: str,
    agent: str,
    limit: int,
    headers: dict[str, str],
) -> list[dict[str, Any]]:
    """Search memories via Mem0 API."""
    try:
        with httpx.Client(timeout=3.0) as client:
            response = client.post(
                f"{MEM0_API_BASE}/memories/search/",
                headers=headers,
                json={
                    "query": query,
                    "user_id": user_id,
                    "limit": limit,
                },
            )
            response.raise_for_status()
            results = response.json()
            # API returns list directly, filter by agent
            if isinstance(results, list):
                return [r for r in results if r.get("metadata", {}).get("agent") == agent][:limit]
            return results.get("results", [])
    except Exception as e:
        logger.warning(f"Memory search failed: {e}")
        return []


def _get_recent_memories(
    user_id: str,
    agent: str,
    limit: int,
    headers: dict[str, str],
) -> list[dict[str, Any]]:
    """Get recent memories via Mem0 API."""
    try:
        with httpx.Client(timeout=3.0) as client:
            response = client.get(
                f"{MEM0_API_BASE}/memories/",
                headers=headers,
                params={
                    "user_id": user_id,
                    "page_size": limit * 3,  # Fetch more to filter by agent
                },
            )
            response.raise_for_status()
            results = response.json()
            # API returns list directly, filter by agent
            if isinstance(results, list):
                return [r for r in results if r.get("metadata", {}).get("agent") == agent][:limit]
            return [r for r in results.get("results", []) if r.get("metadata", {}).get("agent") == agent][:limit]
    except Exception as e:
        logger.warning(f"Get recent memories failed: {e}")
        return []


def get_memory_context(
    user_message: str,
    agent: str = "default",
    user_id: str = "kevin",
    semantic_limit: int = 5,
    temporal_limit: int = 5,
    timeout: float = 3.0,
) -> str:
    """
    Fetch relevant memories via parallel semantic + temporal queries.

    Args:
        user_message: The user's current message (used for semantic search)
        agent: The current agent context (budget, career, etc.)
        user_id: The user identifier
        semantic_limit: Max memories from semantic search
        temporal_limit: Max recent memories
        timeout: Max seconds to wait for memory fetch

    Returns:
        Formatted memory context string, or empty string if unavailable.
    """
    headers = _get_headers()
    if headers is None:
        return ""

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            semantic_future = executor.submit(
                _search_memories, user_message, user_id, agent, semantic_limit, headers
            )
            temporal_future = executor.submit(
                _get_recent_memories, user_id, agent, temporal_limit, headers
            )

            try:
                semantic_results = semantic_future.result(timeout=timeout)
                temporal_results = temporal_future.result(timeout=timeout)
            except FuturesTimeoutError:
                logger.warning("Memory fetch timed out")
                return ""

        # Dedupe by memory ID
        seen_ids: set[str] = set()
        memories: list[str] = []

        # Semantic results first (more relevant)
        for result in semantic_results:
            mem_id = result.get("id", "")
            if mem_id and mem_id not in seen_ids:
                seen_ids.add(mem_id)
                memory_text = result.get("memory", "")
                if memory_text:
                    memories.append(memory_text)

        # Then temporal results (recent context)
        for result in temporal_results:
            mem_id = result.get("id", "")
            if mem_id and mem_id not in seen_ids:
                seen_ids.add(mem_id)
                memory_text = result.get("memory", "")
                if memory_text:
                    memories.append(memory_text)

        if not memories:
            return ""

        return "## What I remember\n" + "\n".join(f"- {m}" for m in memories)

    except Exception as e:
        logger.warning(f"Memory fetch failed: {e}")
        return ""


def save_conversation(
    content: str,
    agent: str = "default",
    user_id: str = "kevin",
    date: str | None = None,
) -> bool:
    """
    Save a conversation to Mem0.

    Args:
        content: The conversation content to save
        agent: The agent context
        user_id: The user identifier
        date: Optional date string (ISO format)

    Returns:
        True if saved successfully, False otherwise.
    """
    headers = _get_headers()
    if headers is None:
        logger.warning("MEM0_API_KEY not set - cannot save conversation")
        return False

    try:
        metadata = {
            "agent": agent,
            "type": "conversation",
            "date": date or datetime.now().strftime("%Y-%m-%d"),
        }

        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                f"{MEM0_API_BASE}/memories/",
                headers=headers,
                json={
                    "messages": [{"role": "user", "content": content}],
                    "user_id": user_id,
                    "metadata": metadata,
                },
            )
            response.raise_for_status()

        logger.info(f"Saved conversation to Mem0 for agent={agent}")
        return True

    except Exception as e:
        logger.error(f"Failed to save conversation to Mem0: {e}")
        return False
