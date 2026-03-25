from __future__ import annotations

import base64
import logging

import httpx
from fastapi import APIRouter, Depends, Request

from apron.api.deps import get_router, get_settings, get_event_bus
from apron.config import Settings
from apron.services.router import MessageRouterService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/webhook/telegram")
async def telegram_webhook(
    request: Request,
    router_service: MessageRouterService = Depends(get_router),
    settings: Settings = Depends(get_settings),
):
    data = await request.json()
    message = data.get("message") or data.get("edited_message")
    if not message:
        return {"ok": True}

    chat_id = str(message["chat"]["id"])
    text = message.get("text", "")
    image_b64 = None
    logger.info("Telegram message from chat_id=%s text=%r has_photo=%s", chat_id, text[:100], bool(message.get("photo")))

    # Handle photo messages
    photos = message.get("photo")
    if photos:
        # Get largest photo (last in array)
        file_id = photos[-1]["file_id"]
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                # Get file path from Telegram
                file_resp = await client.get(
                    f"https://api.telegram.org/bot{settings.telegram_bot_token}/getFile",
                    params={"file_id": file_id},
                )
                file_data = file_resp.json()
                file_path = file_data["result"]["file_path"]

                # Download the file
                download_resp = await client.get(
                    f"https://api.telegram.org/file/bot{settings.telegram_bot_token}/{file_path}"
                )
                if download_resp.status_code < 400:
                    image_b64 = base64.b64encode(download_resp.content).decode("utf-8")
        except Exception:
            logger.exception("Failed to download Telegram photo")

        # Use caption as text if available
        if message.get("caption"):
            text = message["caption"]

    if not text and not image_b64:
        logger.info("Skipping empty message from chat_id=%s", chat_id)
        return {"ok": True}

    logger.info("Dispatching to router: chat_id=%s text=%r has_image=%s", chat_id, text[:100], bool(image_b64))
    await router_service.handle(chat_id, text, image_b64=image_b64)
    logger.info("Router finished for chat_id=%s", chat_id)

    # Emit event for frontend SSE
    event_bus = get_event_bus()
    event_bus.emit("message_processed", {"chat_id": chat_id, "text": text, "has_image": bool(image_b64)})

    # Emit inventory update for frontend
    try:
        from apron.api.deps import get_inventory_repo, get_user_repo
        user_repo = get_user_repo()
        user = await user_repo.get_by_phone(chat_id)
        if user:
            inv_repo = get_inventory_repo()
            items = await inv_repo.get_all(user.id)
            event_bus.emit("inventory_updated", {
                "user_id": str(user.id),
                "items": [item.model_dump(mode="json") for item in items],
            })

            # Store photo and emit photo event for frontend
            if image_b64:
                from apron.api.dashboard import store_photo
                store_photo(str(user.id), image_b64)
                event_bus.emit("photo_received", {
                    "chat_id": chat_id,
                    "image_b64": image_b64,
                })
    except Exception:
        logger.exception("Failed to emit inventory event")

    return {"ok": True}
