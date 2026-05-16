"""Audit log endpoint."""
from fastapi import APIRouter

from db import audit_log

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("")
async def list_audit(project_id: str | None = None, limit: int = 200):
    q = {}
    if project_id:
        q["project_id"] = project_id
    docs = await audit_log.find(q, {"_id": 0}).sort("at", -1).to_list(limit)
    return docs
