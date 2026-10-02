"""FastAPI application factory."""

from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="Mr.Sheven", version="0.1.0", description="酒类评测速查 API")

    from server.app.api.scan import router as scan_router

    app.include_router(scan_router, prefix="/api/v1")

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    return app