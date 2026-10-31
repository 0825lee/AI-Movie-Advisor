from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.profile_schemas import ProfileState
from app.profile_service import ProfileRunner

router = APIRouter(prefix="/profile", tags=["观影画像"])


def get_profile_runner(request: Request) -> ProfileRunner:
    return request.app.state.profile_runner


Runner = Annotated[ProfileRunner, Depends(get_profile_runner)]


@router.get("", response_model=ProfileState)
def get_profile(runner: Runner) -> ProfileState:
    return runner.state()


@router.post("/generate", response_model=ProfileState)
async def generate_profile(runner: Runner) -> ProfileState:
    return runner.start()


@router.post("/rebuild", response_model=ProfileState)
async def rebuild_profile(runner: Runner, request: Request) -> ProfileState:
    request.app.state.import_runner.ensure_idle()
    return await runner.rebuild()
