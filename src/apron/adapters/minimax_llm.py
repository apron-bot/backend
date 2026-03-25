from __future__ import annotations

import logging

from litellm import acompletion

logger = logging.getLogger(__name__)


class MiniMaxLLMAdapter:
    """Implements LLMPort using MiniMax via LiteLLM."""

    def __init__(
        self,
        api_key: str,
        api_base: str = "https://api.minimax.io",
        text_model: str = "minimax/MiniMax-M2.5",
        vision_model: str = "minimax/MiniMax-VL-01",
    ) -> None:
        self._api_key = api_key
        self._api_base = api_base
        self._text_model = text_model
        self._vision_model = vision_model

    async def chat(self, system: str, messages: list[dict], tools: list[dict] | None = None) -> str:
        logger.info("LLM chat model=%s system=%r", self._text_model, system[:80])
        payload = [{"role": "system", "content": system}, *messages]
        try:
            response = await acompletion(
                model=self._text_model,
                messages=payload,
                api_key=self._api_key,
                api_base=self._api_base,
                tools=tools,
                max_tokens=1024,
            )
            result = response.choices[0].message.content or ""
            logger.info("LLM chat response (%d chars): %s", len(result), result[:200])
            return result
        except Exception:
            logger.exception("LLM chat failed model=%s", self._text_model)
            raise

    async def vision(self, system: str, image_b64: str, prompt: str) -> str:
        logger.info("LLM vision model=%s prompt=%r image_size=%d", self._vision_model, prompt[:80], len(image_b64))
        try:
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
            result = response.choices[0].message.content or "[]"
            logger.info("LLM vision response (%d chars): %s", len(result), result[:200])
            return result
        except Exception:
            logger.exception("LLM vision failed model=%s", self._vision_model)
            raise

    async def generate_image(self, prompt: str, style: str = "pixel_art") -> str:
        _ = prompt
        _ = style
        return ""
