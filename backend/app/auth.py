import secrets
from typing import Annotated

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader

internal_header = APIKeyHeader(name="X-Internal-Token", auto_error=False)


def require_internal_token(
    request: Request,
    token: Annotated[str | None, Security(internal_header)],
) -> None:
    expected = request.app.state.settings.movie_internal_token
    if expected is None:
        raise HTTPException(503, "请先在 backend/.env 配置 MOVIE_INTERNAL_TOKEN。")
    if token is None or not secrets.compare_digest(token, expected.get_secret_value()):
        raise HTTPException(401, "内部接口令牌无效。")
