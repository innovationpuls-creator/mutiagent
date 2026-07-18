from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.main import create_app


def create_desktop_app(
    *, database_url: str | None = None, frontend_dist: Path | str
) -> FastAPI:
    frontend_root = Path(frontend_dist).resolve()
    index_path = frontend_root / "index.html"
    if not index_path.is_file():
        raise RuntimeError("桌面版前端入口不存在")

    app = create_app(database_url=database_url)
    assets_dir = frontend_root / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="desktop-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_desktop_frontend(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        requested_path = (frontend_root / full_path).resolve()
        if requested_path.is_relative_to(frontend_root) and requested_path.is_file():
            return FileResponse(requested_path)
        return FileResponse(index_path)

    return app
