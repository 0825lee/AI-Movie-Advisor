import secrets
from contextlib import asynccontextmanager
from typing import Annotated, Any, Literal

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings
from app.database import create_database_engine
from app.dify_client import DifyClient, DifyWorkflowError, WorkflowResult

internal_header = APIKeyHeader(name="X-Internal-Token", auto_error=False)


class HealthResponse(BaseModel):
    status: Literal["ok"]
    database: Literal["ok"]
    database_revision: str
    dify_configured: bool
    tmdb_configured: bool


class DifyCheckRequest(BaseModel):
    inputs: dict[str, Any] = Field(
        default_factory=lambda: {"query": "请用一句话回复：连接成功"}
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = create_database_engine(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(settings.dify_timeout_seconds, connect=10)
        ) as http:
            app.state.http = http
            yield
        engine.dispose()

    app = FastAPI(title="AI Movie Advisor", version="0.1.0", lifespan=lifespan)

    def require_internal_token(
        token: Annotated[str | None, Security(internal_header)],
    ) -> None:
        expected = settings.movie_internal_token
        if expected is None:
            raise HTTPException(503, "请先在 backend/.env 配置 MOVIE_INTERNAL_TOKEN。")
        if token is None or not secrets.compare_digest(token, expected.get_secret_value()):
            raise HTTPException(401, "内部接口令牌无效。")

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        try:
            with engine.connect() as connection:
                revision = connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one()
        except SQLAlchemyError as exc:
            raise HTTPException(503, "数据库未就绪，请先执行 alembic upgrade head。") from exc
        return HealthResponse(
            status="ok",
            database="ok",
            database_revision=revision,
            dify_configured=settings.dify_smoke_api_key is not None,
            tmdb_configured=settings.tmdb_read_access_token is not None,
        )

    @app.get("/internal/health", dependencies=[Depends(require_internal_token)])
    def internal_health() -> dict[str, str]:
        return {"status": "ok", "service": "ai-movie-advisor"}

    @app.post(
        "/internal/dify/check",
        response_model=WorkflowResult,
        dependencies=[Depends(require_internal_token)],
    )
    async def check_dify(body: DifyCheckRequest, request: Request) -> WorkflowResult:
        key = settings.dify_smoke_api_key
        if key is None:
            raise HTTPException(503, "请先配置 DIFY_SMOKE_API_KEY，并确认测试 Workflow 已发布。")
        client = DifyClient(request.app.state.http, settings.dify_base_url)
        try:
            return await client.run_workflow(key.get_secret_value(), body.inputs)
        except httpx.TimeoutException as exc:
            raise HTTPException(504, "Dify 调用超时。") from exc
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                502, "Dify 返回 HTTP " + str(exc.response.status_code) + "，请检查应用 Key 和输入。"
            ) from exc
        except httpx.RequestError as exc:
            raise HTTPException(502, "无法连接 Dify，请检查 18080 服务和 DIFY_BASE_URL。") from exc
        except DifyWorkflowError as exc:
            raise HTTPException(502, str(exc)) from exc

    return app


app = create_app()
