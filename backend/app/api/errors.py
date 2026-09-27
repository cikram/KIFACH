"""One error shape for the whole API: {"error": {"code", "message"}}."""

from __future__ import annotations

from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code, content={"error": {"code": code, "message": message}}
    )


def not_found(message: str) -> ApiError:
    return ApiError(404, "not_found", message)


def bad_request(code: str, message: str) -> ApiError:
    return ApiError(400, code, message)


def conflict(code: str, message: str) -> ApiError:
    return ApiError(409, code, message)
