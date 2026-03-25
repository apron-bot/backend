"""Interactive CLI chat with Bobby (no Twilio needed).

Usage:
    python -m apron.cli_chat
    python -m apron.cli_chat --phone +1234567890

Send a photo by typing the file path:
    You: /path/to/fridge.jpg
    You: ~/Photos/fridge.png

Attach a photo with a message:
    You: /path/to/fridge.jpg here's my fridge
"""

from __future__ import annotations

import asyncio
import base64
import logging
import sys
from pathlib import Path

from apron.api.deps import _container

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


async def main(phone: str) -> None:
    container = _container()
    router = container["router"]

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
    if "--phone" in sys.argv:
        idx = sys.argv.index("--phone")
        if idx + 1 < len(sys.argv):
            phone = sys.argv[idx + 1]
    asyncio.run(main(phone))
