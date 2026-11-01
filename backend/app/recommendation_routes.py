from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.openapi.utils import get_openapi

from app.auth import require_internal_token
from app.catalog_routes import get_catalog
from app.catalog_service import CatalogService
from app.recommendation_runner import RecommendationRunner
from app.recommendation_schemas import (MovieDetailsInput, MovieSearchInput, RecommendationRequest,
                                        RecommendationState, RequestCriteria, VerificationResult, VerifyMoviesInput)
from app.recommendation_service import RecommendationService
from app.verification_service import MovieVerificationService

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


def get_verifier(service: Service) -> MovieVerificationService:
    return MovieVerificationService(service.engine, service.catalog)


Verifier = Annotated[MovieVerificationService, Depends(get_verifier)]


@router.post("/contexts", response_model=RecommendationState)
def prepare_context(body: RecommendationRequest, service: Service) -> RecommendationState:
    """仅创建真实调试任务，不调用模型。将返回的 task_id 填入 Dify 测试输入。"""
    return service.state(service.create(body.request_text))


@router.post("/request", response_model=RecommendationState)
async def recommend(body: RecommendationRequest, service: Service, runner: Runner) -> RecommendationState:
    return runner.start(service.create(body.request_text))


@router.post("/personalized/contexts", response_model=RecommendationState)
def prepare_personalized(service: Service) -> RecommendationState:
    return service.state(service.create_personalized())


@router.post("/personalized", response_model=RecommendationState)
async def recommend_personalized(service: Service, runner: Runner) -> RecommendationState:
    return runner.start(service.create_personalized())


@router.get("/tasks/{task_id}/profile-input")
def personalized_profile_input(task_id: str, service: Service) -> dict:
    """仅返回这个画像推荐任务已固定的快照，供 Dify 预览导出。"""
    return service.profile_input(task_id)


@router.get("/tasks/{task_id}", response_model=RecommendationState)
def read_task(task_id: str, runner: Runner) -> RecommendationState:
    return runner.state(task_id)


@router.get("/tasks/{task_id}/verifications")
def verification_history(task_id: str, verifier: Verifier) -> dict:
    return verifier.history(task_id)


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


@tools_router.post("/verify", operation_id="verify_movies", response_model=VerificationResult,
                   summary="批量核实 Agent 提名电影、硬条件和观看状态")
async def verify_movies(body: VerifyMoviesInput, verifier: Verifier) -> VerificationResult:
    """首次提交 constraints（无硬条件提交 {}）；后续省略复用。每批最多 8 部，最终只选择 eligible_movie_ids 中的本地 ID。"""
    return await verifier.verify(body)


def build_tools_schema(port: int) -> dict:
    schema = get_openapi(title="Movie Advisor Recommendation Tools", version="1.0.0",
                         routes=[route for route in tools_router.routes if route.operation_id == "verify_movies"],
                         servers=[{"url": f"http://host.docker.internal:{port}"}])
    # 本机 Dify 的 Swagger 解析器不保留嵌套对象 schema，导出为明确的 JSON 文本参数。
    body = schema["components"]["schemas"]["VerifyMoviesInput"]["properties"]
    body["movies"] = {"type": "string", "description": 'JSON 数组文本，每批 1～8 部；例如 [{"title":"诗","original_title":"시","year":2010}]。只填你提名的电影。'}
    body["constraints"] = {"type": "string", "description": '硬条件 JSON 对象文本，首次无条件提交 "{}"，后续省略复用；支持 directors/actors/year_from/year_to/runtime_min/runtime_max/countries/languages/required_genres/excluded_genres。人物填姓名，国家两位大写代码、语言两位小写代码、类型用 TMDB 中文名。所有列表按任一符合，排除类型均不能命中。'}
    return schema


@router.get("/tools/openapi.json", include_in_schema=False)
def movie_tools_schema(request: Request) -> dict:
    return build_tools_schema(request.app.state.settings.backend_port)
