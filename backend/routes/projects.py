"""Project CRUD endpoints."""
from fastapi import APIRouter, HTTPException
from typing import List
from datetime import datetime, timezone

from db import projects, audit_log
from models import Project, ProjectCreate

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=Project)
async def create_project(payload: ProjectCreate):
    proj = Project(**payload.model_dump())
    await projects.insert_one(proj.model_dump())
    await audit_log.insert_one({
        "action": "project.create",
        "project_id": proj.id,
        "at": datetime.now(timezone.utc).isoformat(),
        "details": {"name": proj.name},
    })
    return proj


@router.get("", response_model=List[Project])
async def list_projects():
    docs = await projects.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return [Project(**d) for d in docs]


@router.get("/{project_id}", response_model=Project)
async def get_project(project_id: str):
    doc = await projects.find_one({"id": project_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Project not found")
    return Project(**doc)
