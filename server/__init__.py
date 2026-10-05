"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shared.log_setup import setup_service_logging


def create_app() -> FastAPI:
    # 日志规范化：落盘 ./logs/backend/（滚动文件 + 控制台，含 uvicorn access）
    setup_service_logging("backend")

    app = FastAPI(title="Mr.Sheven", version="0.1.0", description="酒类评测速查 API")

    # CORS: allow Flutter Web (dev)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from server.api.scan import router as scan_router

    app.include_router(scan_router, prefix="/api/v1")

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    return app