from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

import httpx
from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_ROOT / ".env")

DIFY_API_URL = os.getenv("DIFY_API_URL", "http://localhost/v1")
DIFY_CHAT_API_KEY = os.getenv("DIFY_CHAT_API_KEY", "")
DIFY_PROFILE_AGENT_API_KEY = os.getenv("DIFY_PROFILE_AGENT_API_KEY", "")
DIFY_INTENT_RECOGNITION_API_KEY = os.getenv("DIFY_INTENT_RECOGNITION_API_KEY", "")
DIFY_LEARNING_PATH_AGENT_API_KEY = os.getenv("DIFY_LEARNING_PATH_AGENT_API_KEY", "")


@dataclass
class DifyResponse:
    answer: str
    conversation_id: str
    task_id: str
    message_id: str
    raw: dict


class DifyClient:
    def __init__(self, base_url: str = DIFY_API_URL, api_key: str = DIFY_PROFILE_AGENT_API_KEY) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    async def chat_blocking(
        self,
        query: str,
        user_id: str,
        conversation_id: str = "",
        inputs: dict | None = None,
    ) -> DifyResponse:
        url = f"{self._base_url}/chat-messages"
        payload = {
            "inputs": inputs or {},
            "query": query,
            "response_mode": "blocking",
            "conversation_id": conversation_id,
            "user": user_id,
        }

        if not self._api_key:
            raise RuntimeError("Dify API key is not configured")

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        return DifyResponse(
            answer=data.get("answer", ""),
            conversation_id=data.get("conversation_id", ""),
            task_id=data.get("task_id", ""),
            message_id=data.get("message_id", ""),
            raw=data,
        )

    async def chat_streaming(
        self,
        query: str,
        user_id: str,
        conversation_id: str = "",
        inputs: dict | None = None,
    ):
        url = f"{self._base_url}/chat-messages"
        payload = {
            "inputs": inputs or {},
            "query": query,
            "response_mode": "streaming",
            "conversation_id": conversation_id,
            "user": user_id,
        }

        if not self._api_key:
            raise RuntimeError("Dify API key is not configured")

        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        yield line[6:]
