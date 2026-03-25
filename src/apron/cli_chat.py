"""Interactive CLI chat with Bobby (no Twilio needed).

Usage:
    python -m apron.cli_chat
    python -m apron.cli_chat --skip-onboarding
    python -m apron.cli_chat --phone +1234567890

Send a photo by typing the file path:
    You: /path/to/fridge.jpg
    You: ~/Photos/fridge.png here's my fridge
"""

from __future__ import annotations

import asyncio
import base64
import logging
import sys
from pathlib import Path

from apron.api.deps import _container
from apron.domain.enums import ConversationState

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(message)s",
    datefmt="%H:%M:%S",
)
# Quiet noisy libs, keep our messaging logs visible
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("google").setLevel(logging.WARNING)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}


def _parse_input(raw: str) -> tuple[str, str | None]:
    """Return (text, image_b64 | None) from user input.

    If the first token is a path to an image file, read and base64-encode it.
    The rest of the line becomes the text message (or empty string).
    """
    parts = raw.split(maxsplit=1)
    if not parts:
        return "", None

    candidate = Path(parts[0]).expanduser()
    if candidate.is_file() and candidate.suffix.lower() in IMAGE_EXTENSIONS:
        image_b64 = base64.b64encode(candidate.read_bytes()).decode("utf-8")
        text = parts[1] if len(parts) > 1 else ""
        print(f"  (attached {candidate.name})")
        return text, image_b64

    return raw, None


async def _skip_onboarding(container: dict, phone: str) -> None:
    """Create a user and fast-forward past onboarding to idle state."""
    from datetime import timezone
    from uuid import uuid4
    from apron.domain.models import UserProfile

    user_repo = container["user_repo"]
    existing = await user_repo.get_by_phone(phone)
    if existing and existing.conversation_state != ConversationState.ONBOARDING:
        print("(user already past onboarding)")
        return

    from apron.ports.clock import ClockPort

    now = __import__("datetime").datetime.now(timezone.utc)
    user = (existing or UserProfile(
        id=uuid4(),
        phone_number=phone,
        created_at=now,
        updated_at=now,
    )).model_copy(update={
        "conversation_state": ConversationState.IDLE,
        "onboarding_step": 0,
        "updated_at": now,
    })
    if existing:
        await user_repo.update(user)
    else:
        await user_repo.save(user)
    print("(onboarding skipped — starting in idle state)")


async def main(phone: str, skip_onboarding: bool = False) -> None:
    container = _container()
    router = container["router"]

    if skip_onboarding:
        await _skip_onboarding(container, phone)

    print(f"Chatting as {phone}  (type 'quit' to exit)")
    print("Tip: send a photo by typing its file path\n")

    while True:
        try:
            raw = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break
        if raw.lower() in {"quit", "exit", "q"}:
            print("Bye!")
            break
        if not raw:
            continue
        text, image_b64 = _parse_input(raw)
        await router.handle(phone, text, image_b64=image_b64)


if __name__ == "__main__":
    phone = "+0000000000"
    skip = "--skip-onboarding" in sys.argv or "--skip" in sys.argv
    if "--phone" in sys.argv:
        idx = sys.argv.index("--phone")
        if idx + 1 < len(sys.argv):
            phone = sys.argv[idx + 1]
    asyncio.run(main(phone, skip_onboarding=skip))
