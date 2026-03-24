from fastapi import FastAPI

from apron.api.dashboard import router as dashboard_router
from apron.api.webhook import router as webhook_router


def create_app() -> FastAPI:
    app = FastAPI(title="Apron")
    app.include_router(webhook_router)
    app.include_router(dashboard_router, prefix="/dashboard")
    return app


app = create_app()
