"""Production ASGI entry point serving the API and built web UI together."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import FastAPI
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.staticfiles import StaticFiles

from backend.api.app import app as api_app


def bundled_root() -> Path:
    """Return the source root or PyInstaller extraction root."""

    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[1]


def default_static_root() -> Path:
    override = os.environ.get("GFM_STATIC_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return bundled_root() / "apps" / "web" / "dist"


class SinglePageApplicationFiles(StaticFiles):
    """Serve index.html for client-side routes while preserving real 404s."""

    async def get_response(self, path: str, scope: dict):  # type: ignore[no-untyped-def]
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as error:
            if error.status_code != 404 or "." in Path(path).name:
                raise
            return await super().get_response("index.html", scope)


def create_production_app(
    static_root: str | Path | None = None,
    *,
    base_app: FastAPI | None = None,
) -> FastAPI:
    """Attach the compiled frontend after all API routes.

    The explicit existence check makes a missing frontend build fail at startup
    instead of silently exposing an API-only release.
    """

    resolved_static_root = Path(static_root or default_static_root()).resolve()
    index_file = resolved_static_root / "index.html"
    if not index_file.is_file():
        raise RuntimeError(
            "Production frontend is missing: "
            f"{index_file}. Run scripts/build_release.ps1."
        )

    target = base_app or api_app
    target.mount(
        "/",
        SinglePageApplicationFiles(directory=resolved_static_root, html=True),
        name="production-web",
    )
    return target
