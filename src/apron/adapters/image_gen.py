
from __future__ import annotations

from openai import OpenAI


class OpenAIImageAdapter:
    def __init__(self, api_key: str):
        self._client = OpenAI(api_key=api_key)

    async def generate_image(self, prompt: str, style: str = "pixel_art") -> str:
        full_prompt = (
            f"{style} style food illustration of {prompt}, Cooking Mama aesthetic, "
            "vibrant colors, white background"
        )
        response = self._client.images.generate(model="gpt-image-1", prompt=full_prompt, size="1024x1024")
        return response.data[0].url if response.data else ""
