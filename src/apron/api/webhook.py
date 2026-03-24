
import base64

import httpx
from fastapi import APIRouter, Depends, Request, Response

from apron.api.deps import get_router, get_settings
from apron.config import Settings
from apron.services.router import MessageRouterService

router = APIRouter()


@router.post("/webhook/twilio")
async def twilio_webhook(
    request: Request,
    router_service: MessageRouterService = Depends(get_router),
    settings: Settings = Depends(get_settings),
):
    form = await request.form()
    from_value = str(form.get("From", "")).replace("whatsapp:", "")
    body = str(form.get("Body", ""))
    num_media = int(str(form.get("NumMedia", "0")))
    image_b64 = None
    if num_media > 0 and "image" in str(form.get("MediaContentType0", "")):
        media_url = str(form.get("MediaUrl0", ""))
        if media_url:
            async with httpx.AsyncClient(timeout=20) as client:
                media_response = await client.get(
                    media_url,
                    auth=(settings.twilio_account_sid, settings.twilio_auth_token),
                )
                if media_response.status_code < 400:
                    image_b64 = base64.b64encode(media_response.content).decode("utf-8")
    await router_service.handle(from_value, body, image_b64=image_b64)
    return Response(content="<Response></Response>", media_type="application/xml")
