from __future__ import annotations

from litellm import acompletion


class MiniMaxLLMAdapter:
    """Implements LLMPort using MiniMax via LiteLLM."""

    def __init__(
        self,
        api_key: str,
        api_base: str = "https://api.minimax.io/anthropic/v1/messages",
        text_model: str = "minimax/MiniMax-M2.5",
        vision_model: str = "minimax/MiniMax-VL-01",
    ) -> None:
        self._api_key = api_key
        self._api_base = api_base
        self._text_model = text_model
        self._vision_model = vision_model

    async def chat(self, system: str, messages: list[dict], tools: list[dict] | None = None) -> str:
        payload = [{"role": "system", "content": system}, *messages]
        response = await acompletion(
            model=self._text_model,
            messages=payload,
            api_key=self._api_key,
            api_base=self._api_base,
            tools=tools,
            max_tokens=1024,
        )
        return response.choices[0].message.content or ""

    async def vision(self, system: str, image_b64: str, prompt: str) -> str:
        response = await acompletion(
            model=self._vision_model,
            messages=[
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                    ],
                },
            ],
            api_key=self._api_key,
            api_base=self._api_base,
            max_tokens=1024,
        )
        return response.choices[0].message.content or "[]"

    async def generate_image(self, prompt: str, style: str = "pixel_art") -> str:
        _ = prompt
        _ = style
        return ""
