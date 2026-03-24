from typing import Protocol


class LLMPort(Protocol):
    async def chat(
        self, system: str, messages: list[dict], tools: list[dict] | None = None
    ) -> str: ...

    async def vision(self, system: str, image_b64: str, prompt: str) -> str: ...

    async def generate_image(self, prompt: str, style: str = "pixel_art") -> str: ...
