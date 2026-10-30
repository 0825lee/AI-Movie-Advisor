from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.catalog_routes import get_catalog
from app.catalog_schemas import CatalogRef, SearchType
from app.catalog_service import CatalogService
from app.library_schemas import ClearLibraryResult, LibraryEntry, LibraryPage, LibraryState, LibraryStatus, ManualAdd, MarkWatched
from app.library_service import LibraryService

router = APIRouter(prefix="/library", tags=["我的片库"])


def get_library(request: Request, catalog: Annotated[CatalogService, Depends(get_catalog)]) -> LibraryService:
    return LibraryService(request.app.state.engine, catalog)


Service = Annotated[LibraryService, Depends(get_library)]


@router.get("", response_model=LibraryPage)
def list_library(
    service: Service, status: LibraryStatus = "watched", media_type: SearchType = "all",
    query: str = "", page: int = Query(default=1, ge=1),
) -> LibraryPage:
    return service.list(status, media_type, query, page)


@router.get("/state", response_model=LibraryState)
def get_library_state(ref: Annotated[CatalogRef, Query()], service: Service) -> LibraryState:
    return service.state(ref)


@router.delete("", response_model=ClearLibraryResult)
def clear_library(service: Service) -> ClearLibraryResult:
    """清空想看、看过及个人评分，保留作品资料缓存。"""
    return ClearLibraryResult(deleted=service.clear())


@router.post("/manual", response_model=LibraryEntry)
async def add_manual(body: ManualAdd, service: Service) -> LibraryEntry:
    return await service.add(body)


@router.post("/{item_id}/watched", response_model=LibraryEntry)
def mark_watched(item_id: int, body: MarkWatched, service: Service) -> LibraryEntry:
    return service.mark_watched(item_id, body.rating)
