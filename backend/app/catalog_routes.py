from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.auth import require_internal_token
from app.catalog_schemas import (
    CatalogDetail, CatalogPage, CatalogRef, ConfirmRequest, MatchRequest, MatchResult,
    SearchResult, SearchType,
)
from app.catalog_service import CatalogService

router = APIRouter(prefix="/catalog", tags=["作品资料"])
tools_router = APIRouter(
    prefix="/internal/movies", tags=["电影只读工具"],
    dependencies=[Depends(require_internal_token)],
)


def get_catalog(request: Request) -> CatalogService:
    return CatalogService(request.app.state.engine, request.app.state.tmdb)


Service = Annotated[CatalogService, Depends(get_catalog)]


@router.get("/search", response_model=SearchResult)
async def search_catalog(
    service: Service, query: str = Query(min_length=1),
    media_type: SearchType = "all", year: int | None = None, page: int = Query(default=1, ge=1),
) -> SearchResult:
    return await service.search(query, media_type, year, page)


@router.get("/details", response_model=CatalogDetail)
async def get_details(
    ref: Annotated[CatalogRef, Query()], service: Service, refresh: bool = False,
) -> CatalogDetail:
    return await service.detail(ref, refresh)


@router.post("/confirm", response_model=CatalogDetail)
async def confirm_catalog(body: ConfirmRequest, service: Service) -> CatalogDetail:
    return await service.confirm(body)


@router.get("/items", response_model=CatalogPage)
def list_catalog(service: Service, page: int = Query(default=1, ge=1)) -> CatalogPage:
    return service.confirmed_items(page)


@router.post("/match", response_model=MatchResult)
async def match_catalog(body: MatchRequest, service: Service) -> MatchResult:
    return await service.match(body)


@tools_router.get("/search", response_model=SearchResult, operation_id="search_movies")
async def search_movies(
    service: Service, query: str = Query(min_length=1),
    year: int | None = None, page: int = Query(default=1, ge=1),
) -> SearchResult:
    """按名称搜索电影；只读工具，不修改个人片库。"""
    return await service.search(query, "movie", year, page)


@tools_router.get("/{tmdb_id}", response_model=CatalogDetail, operation_id="get_movie_details")
async def get_movie_details(service: Service, tmdb_id: int) -> CatalogDetail:
    """读取电影详情；资料可以缓存，不修改个人片库。"""
    return await service.detail(CatalogRef(media_type="movie", tmdb_id=tmdb_id))
