
from __future__ import annotations

from twilio.rest import Client


class TwilioWhatsAppAdapter:
    """Implements MessagingPort using Twilio WhatsApp Business API."""

    def __init__(self, account_sid: str, auth_token: str, from_number: str):
        self._client = Client(account_sid, auth_token)
        self._from = from_number

    async def send_text(self, to: str, body: str) -> None:
        for chunk in self._split_message(body, max_chars=1600):
            self._client.messages.create(to=f"whatsapp:{to}", from_=self._from, body=chunk)

    async def send_image(self, to: str, image_url: str, caption: str) -> None:
        self._client.messages.create(
            to=f"whatsapp:{to}",
            from_=self._from,
            body=caption,
            media_url=[image_url],
        )

    async def send_template(self, to: str, template: str, params: dict) -> None:
        rendered = template.format(**params)
        await self.send_text(to, rendered)

    @staticmethod
    def _split_message(body: str, max_chars: int = 1600) -> list[str]:
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
