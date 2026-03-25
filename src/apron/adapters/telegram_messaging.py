from __future__ import annotations
import httpx

class TelegramMessagingAdapter:
    """Implements MessagingPort using the Telegram Bot API."""

    BASE_URL = "https://api.telegram.org/bot{token}"

    def __init__(self, bot_token: str):
        self._token = bot_token
        self._base = self.BASE_URL.format(token=bot_token)

    async def send_text(self, to: str, body: str) -> None:
        # Telegram max message is 4096 chars
        for chunk in self._split_message(body, max_chars=4096):
            async with httpx.AsyncClient(timeout=15) as client:
                await client.post(
                    f"{self._base}/sendMessage",
                    json={"chat_id": to, "text": chunk, "parse_mode": "Markdown"},
                )

    async def send_image(self, to: str, image_url: str, caption: str) -> None:
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(
                f"{self._base}/sendPhoto",
                json={"chat_id": to, "photo": image_url, "caption": caption},
            )

    async def send_template(self, to: str, template: str, params: dict) -> None:
        rendered = template.format(**params)
        await self.send_text(to, rendered)

    @staticmethod
    def _split_message(body: str, max_chars: int = 4096) -> list[str]:
        if len(body) <= max_chars:
            return [body]
        chunks: list[str] = []
        words = body.split()
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if len(candidate) > max_chars:
                chunks.append(current)
                current = word
            else:
                current = candidate
        if current:
            chunks.append(current)
        return chunks
