"""新 M1 API 的统一错误封套：`{code, retryable, visible, message}`。"""

from fastapi import Request
from fastapi.responses import JSONResponse

from backend.domain.errors import ErrorCode
from backend.tools.gateway import error_envelope


class ApiError(Exception):
    """带 HTTP 状态码与错误码的业务异常；由应用级 handler 转封套。"""

    def __init__(
        self,
        status_code: int,
        code: ErrorCode,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(code.value)
        self.status_code = status_code
        self.code = code
        self.headers = headers


async def api_error_handler(_request: Request, error: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content=error_envelope(error.code),
        headers=error.headers,
    )
