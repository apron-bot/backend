
from __future__ import annotations

from anthropic import AsyncAnthropic
from openai import OpenAI


class ClaudeLLMAdapter:
    """Implements LLMPort using Anthropic SDK."""

    def __init__(self, api_key: str, openai_api_key: str = "", model: str = "claude-sonnet-4-20250514"):
        self._client = AsyncAnthropic(api_key=api_key)
        self._openai = OpenAI(api_key=openai_api_key) if openai_api_key else None
        self._model = model

    async def chat(self, system: str, messages: list[dict], tools: list[dict] | None = None) -> str:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=system,
            tools=tools or [],
            messages=messages,
        )
        if response.content:
            return response.content[0].text
        return ""

    async def vision(self, system: str, image_b64: str, prompt: str) -> str:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=system,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": image_b64,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
        if response.content:
            return response.content[0].text
        return "[]"

    async def generate_image(self, prompt: str, style: str = "pixel_art") -> str:
        if not self._openai:
            return ""
        text = (
            f"{style} style food illustration of {prompt}, Cooking Mama aesthetic, "
            "vibrant colors, white background"
        )
        image = self._openai.images.generate(model="gpt-image-1", prompt=text, size="1024x1024")
        return image.data[0].url if image.data else ""
