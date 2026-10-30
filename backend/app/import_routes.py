from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request

from app.import_schemas import ImportOutcome, ImportRequest, ImportRowsPage, ImportSummary
from app.import_service import ImportRunner

router = APIRouter(prefix="/imports", tags=["豆瓣 JSON 导入"])


def get_runner(request: Request) -> ImportRunner:
    return request.app.state.import_runner


Runner = Annotated[ImportRunner, Depends(get_runner)]


@router.post("", response_model=ImportSummary)
async def create_import(body: ImportRequest, runner: Runner) -> ImportSummary:
    return runner.create(body)


@router.get("", response_model=list[ImportSummary])
def list_imports(runner: Runner) -> list[ImportSummary]:
    return runner.jobs()


@router.get("/{job_id}", response_model=ImportSummary)
def get_import(job_id: int, runner: Runner) -> ImportSummary:
    return runner.summary(job_id)


@router.get("/{job_id}/rows", response_model=ImportRowsPage)
def get_import_rows(
    job_id: int, runner: Runner, outcome: Literal["all"] | ImportOutcome = "all",
    page: int = Query(default=1, ge=1),
) -> ImportRowsPage:
    return runner.rows(job_id, outcome, page)


@router.post("/{job_id}/resume", response_model=ImportSummary)
async def resume_import(job_id: int, runner: Runner) -> ImportSummary:
    return runner.resume(job_id)


@router.post("/{job_id}/pause", response_model=ImportSummary)
async def pause_import(job_id: int, runner: Runner) -> ImportSummary:
    return await runner.pause(job_id)
