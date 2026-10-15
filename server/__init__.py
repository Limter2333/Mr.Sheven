"""FastAPI application factory."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

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

    from server.api.feedback import router as feedback_router
    from server.api.scan import router as scan_router

    app.include_router(scan_router, prefix="/api/v1")
    app.include_router(feedback_router, prefix="/api/v1")

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    # 单映射部署：flutter build web 产物同源托管（须在 API 路由之后挂载）。
    # 花生壳等内网穿透只需映射本端口一个端口；前端发布版默认走页面地址，免配置。
    web_dist = Path(__file__).resolve().parent.parent / "app" / "build" / "web"
    if web_dist.is_dir():
        app.mount("/", StaticFiles(directory=str(web_dist), html=True), name="web")
    else:

        @app.get("/")
        async def web_not_built():
            return {
                "hint": "前端未构建：先执行 cd app && flutter build web，重启后端即可同源访问"
            }

    return app