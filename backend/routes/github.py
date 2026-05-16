"""GitHub push endpoint — stub for now."""
from fastapi import APIRouter
from models import GithubPushRequest

router = APIRouter(prefix="/github", tags=["github"])


@router.post("/push")
async def push_to_github(payload: GithubPushRequest):
    # Stubbed: actual implementation deferred to Stage 4 (CodeGen).
    return {
        "status": "success",
        "message": "GitHub push will be implemented in Stage 4",
        "project_id": payload.project_id,
        "repo_url": payload.repo_url,
        "branch": payload.branch,
    }
