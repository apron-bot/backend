from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apron.api.dashboard import router as dashboard_router
from apron.api.webhook import router as webhook_router
from apron.api.telegram_webhook import router as telegram_router
from apron.api.streaming import router as streaming_router


def create_app() -> FastAPI:
    app = FastAPI(title="Apron")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(webhook_router)
    app.include_router(telegram_router)
    app.include_router(dashboard_router, prefix="/dashboard")
    app.include_router(streaming_router)
    return app


app = create_app()
