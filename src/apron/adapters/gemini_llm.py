from __future__ import annotations

import httpx


class GeminiLLMAdapter:
    """Implements LLMPort using Gemini Developer API (REST)."""

    def __init__(self, api_key: str, model: str = "gemini-1.5-flash"):
        self._api_key = api_key
        self._model = model
        self._base_url = "https://generativelanguage.googleapis.com/v1beta/models"

    async def chat(self, system: str, messages: list[dict], tools: list[dict] | None = None) -> str:
        _ = tools
        rendered_messages: list[str] = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            rendered_messages.append(f"{role}: {content}")
        prompt = f"System:\n{system}\n\nConversation:\n" + "\n".join(rendered_messages)
        return await self._generate_text(prompt)

    async def vision(self, system: str, image_b64: str, prompt: str) -> str:
        url = f"{self._base_url}/{self._model}:generateContent?key={self._api_key}"
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": f"{system}\n\n{prompt}"},
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": image_b64,
                            }
                        },
                    ]
                }
            ]
        }
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
        return self._extract_text(response.json())

    async def generate_image(self, prompt: str, style: str = "pixel_art") -> str:
        _ = style
        _ = prompt
        return ""

    async def _generate_text(self, prompt: str) -> str:
        url = f"{self._base_url}/{self._model}:generateContent?key={self._api_key}"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
        return self._extract_text(response.json())

    @staticmethod
    def _extract_text(payload: dict) -> str:
        candidates = payload.get("candidates", [])
        if not candidates:
            return ""
        parts = candidates[0].get("content", {}).get("parts", [])
        texts = [p.get("text", "") for p in parts if isinstance(p, dict)]
        return "".join(texts).strip()
