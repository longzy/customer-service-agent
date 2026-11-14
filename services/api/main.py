"""Conversation API 的最小入口。M1 阶段只提供健康检查。"""

from fastapi import FastAPI

from services.api.settings import settings


def create_app() -> FastAPI:
    app = FastAPI(title="Customer Service Agent API", version="0.1.0")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "confirm_timeout_minutes": str(settings.confirm_timeout_minutes)}

    return app


app = create_app()
