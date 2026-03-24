
from fastapi import APIRouter, Depends, Request

from apron.api.deps import get_router
from apron.services.router import MessageRouterService

router = APIRouter()


@router.post("/webhook/twilio")
async def twilio_webhook(
    request: Request,
    router_service: MessageRouterService = Depends(get_router),
):
    form = await request.form()
    from_value = str(form.get("From", "")).replace("whatsapp:", "")
    body = str(form.get("Body", ""))
    num_media = int(str(form.get("NumMedia", "0")))
    image_b64 = None
    if num_media > 0 and "image" in str(form.get("MediaContentType0", "")):
        image_b64 = str(form.get("MediaUrl0", ""))
    await router_service.handle(from_value, body, image_b64=image_b64)
    return {"ok": True}
