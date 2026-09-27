"""FastAPI application factory.

In development the frontend runs under Vite and proxies /api here. In the
delivered app this process also serves the built frontend, so one command on
port 8000 is the whole product.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import api_router
from app.api.errors import ApiError, error_response
from app.config import REPO_ROOT, VERSION, get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("kifach")


def create_app() -> FastAPI:
    settings = get_settings()
    settings.ensure_dirs()

    app = FastAPI(
        title="KIFACH",
        version=VERSION,
        description=(
            "Show once. Teach forever. An expert demonstration becomes a reviewed "
            "procedure; a learner attempt is assessed against it with evidence."
        ),
    )

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return error_response(exc.status_code, exc.code, exc.message)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
        code = {404: "not_found", 405: "method_not_allowed", 413: "payload_too_large"}.get(
            exc.status_code, "http_error"
        )
        return error_response(exc.status_code, code, detail)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        location = ".".join(str(part) for part in first.get("loc", ())[1:])
        message = first.get("msg", "The request body is invalid.")
        return error_response(
            422,
            "invalid_request",
            f"{location}: {message}" if location else message,
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:  # pragma: no cover
        log.exception("Unhandled error")
        return error_response(
            500,
            "internal_error",
            "Something went wrong on the server. The server log has the details.",
        )

    app.include_router(api_router, prefix="/api")

    # Bundled demo footage, so Demo Mode needs no upload and no network.
    samples = REPO_ROOT / "samples"
    if samples.exists():
        app.mount("/samples", StaticFiles(directory=samples), name="samples")

    dist = settings.frontend_dist
    if dist.exists():
        assets = dist / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False, response_model=None)
        async def spa(full_path: str) -> Response:
            candidate = (dist / full_path).resolve()
            if full_path and candidate.is_file():
                try:
                    candidate.relative_to(dist.resolve())
                except ValueError:
                    return error_response(404, "not_found", "Not found.")
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")

    else:

        @app.get("/", include_in_schema=False)
        async def no_frontend() -> JSONResponse:
            return JSONResponse(
                {
                    "message": (
                        "The API is running. The frontend has not been built yet: "
                        "run `npm --prefix frontend install && npm --prefix frontend "
                        "run build`, or use the Vite dev server on port 5173."
                    ),
                    "docs": "/docs",
                    "health": "/api/health",
                }
            )

    return app


app = create_app()
