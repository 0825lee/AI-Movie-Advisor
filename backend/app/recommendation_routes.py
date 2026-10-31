from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.openapi.utils import get_openapi

from app.auth import require_internal_token
from app.catalog_routes import get_catalog
from app.catalog_service import CatalogService
from app.recommendation_runner import RecommendationRunner
from app.recommendation_schemas import (MovieDetailsInput, MovieSearchInput, RecommendationRequest,
                                        RecommendationState, RequestCriteria)
from app.recommendation_service import RecommendationService

router = APIRouter(prefix="/recommendations", tags=["本次需求推荐"])
tools_router = APIRouter(prefix="/internal/movie-tools", tags=["推荐只读工具"],
                         dependencies=[Depends(require_internal_token)])
context_router = APIRouter(prefix="/internal/recommendation-contexts", tags=["推荐任务条件"],
                           dependencies=[Depends(require_internal_token)])


def get_service(request: Request, catalog: Annotated[CatalogService, Depends(get_catalog)]) -> RecommendationService:
    return RecommendationService(request.app.state.engine, catalog)


def get_runner(request: Request) -> RecommendationRunner:
    return request.app.state.recommendation_runner


Service = Annotated[RecommendationService, Depends(get_service)]
Runner = Annotated[RecommendationRunner, Depends(get_runner)]


@router.post("/contexts", response_model=RecommendationState)
def prepare_context(body: RecommendationRequest, service: Service) -> RecommendationState:
    """仅创建真实调试任务，不调用模型。将返回的 task_id 填入 Dify 测试输入。"""
    return service.state(service.create(body.request_text))


@router.post("/request", response_model=RecommendationState)
async def recommend(body: RecommendationRequest, service: Service, runner: Runner) -> RecommendationState:
    return runner.start(service.create(body.request_text))


@router.get("/tasks/{task_id}", response_model=RecommendationState)
def read_task(task_id: str, runner: Runner) -> RecommendationState:
    return runner.state(task_id)


@router.post("/tasks/{task_id}/run", response_model=RecommendationState)
async def run_task(task_id: str, runner: Runner) -> RecommendationState:
    """执行准备好的任务，或重试失败的任务。"""
    return runner.start(task_id)


@context_router.post("/{task_id}/criteria")
async def register_criteria(task_id: str, body: RequestCriteria, service: Service) -> dict:
    return await service.register_criteria(task_id, body)


@tools_router.post("/search", operation_id="recommendation_search_movies", summary="按任务条件检索真实电影候选")
async def search_movies(body: MovieSearchInput, service: Service) -> dict:
    """绑定上游 task_id 和 target_count；后端执行看过／屏蔽／本批次去重及正向条件放宽。"""
    return await service.search(body.task_id, body.target_count)


@tools_router.post("/details", operation_id="recommendation_get_movie_details", summary="读取本任务候选的电影详情")
async def get_movie_details(body: MovieDetailsInput, service: Service) -> dict:
    """movie_id 必须取自 search_movies 的结果，不得使用 TMDB ID 或自行编造。"""
    return await service.detail(body.task_id, body.movie_id)


def build_tools_schema(port: int) -> dict:
    schema = get_openapi(title="Movie Advisor Recommendation Tools", version="1.0.0",
                         routes=tools_router.routes, servers=[{"url": f"http://host.docker.internal:{port}"}])
    # 专用工具包继续使用这两个短名称，主应用 OpenAPI 与旧 GET 工具保持不同 operationId。
    schema["paths"]["/internal/movie-tools/search"]["post"]["operationId"] = "search_movies"
    schema["paths"]["/internal/movie-tools/details"]["post"]["operationId"] = "get_movie_details"
    return schema


@router.get("/tools/openapi.json", include_in_schema=False)
def movie_tools_schema(request: Request) -> dict:
    return build_tools_schema(request.app.state.settings.backend_port)
