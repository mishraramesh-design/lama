"""GitHub config + test + push endpoints."""
import os
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

import requests

from db import projects, srs_documents, audit_log
from models import GithubPushRequest

router = APIRouter(prefix="/github", tags=["github"])


class GithubConfig(BaseModel):
    project_id: str
    repo_url: str
    token: str
    branch: str = "main"


class GithubTestRequest(BaseModel):
    repo_url: str = ""
    token: str


def _parse_repo(repo_url: str) -> tuple[str, str]:
    """Parse 'https://github.com/owner/repo[.git]' into (owner, repo)."""
    url = (repo_url or "").strip().rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    parts = url.replace("https://", "").replace("http://", "").split("/")
    # github.com / owner / repo
    if len(parts) < 3 or "github" not in parts[0]:
        raise HTTPException(400, "Invalid GitHub repo URL")
    return parts[-2], parts[-1]


@router.post("/config")
async def save_config(payload: GithubConfig):
    """Save GitHub config to the project document (token stored — caller acknowledged)."""
    proj = await projects.find_one({"id": payload.project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(404, "Project not found")
    await projects.update_one(
        {"id": payload.project_id},
        {"$set": {
            "github_repo": payload.repo_url,
            "github_token": payload.token,
            "github_branch": payload.branch,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    return {"ok": True}


@router.get("/config/{project_id}")
async def get_config(project_id: str):
    proj = await projects.find_one({"id": project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(404, "Project not found")
    token = proj.get("github_token", "")
    return {
        "repo_url": proj.get("github_repo", ""),
        "branch": proj.get("github_branch", "main"),
        "has_token": bool(token),
        "token_preview": (token[:6] + "…") if token else "",
    }


@router.post("/test")
async def test_connection(payload: GithubTestRequest):
    """Fetch repo metadata to verify token + URL."""
    try:
        owner, repo = _parse_repo(payload.repo_url)
    except HTTPException as e:
        return {"ok": False, "error": e.detail}
    try:
        r = requests.get(
            f"https://api.github.com/repos/{owner}/{repo}",
            headers={
                "Authorization": f"token {payload.token}",
                "Accept": "application/vnd.github+json",
            },
            timeout=15,
        )
    except Exception as e:
        return {"ok": False, "error": str(e)}
    if r.status_code != 200:
        return {"ok": False, "error": f"GitHub API {r.status_code}: {r.text[:200]}"}
    data = r.json()
    return {
        "ok": True,
        "repo_name": data.get("full_name"),
        "private": data.get("private"),
        "default_branch": data.get("default_branch"),
    }


def _srs_to_markdown(project: dict, srs: dict) -> str:
    sec = srs.get("sections", {})
    order = [
        ("purpose", "1. Purpose"),
        ("scope", "2. Scope"),
        ("definitions", "3. Definitions, Acronyms & Abbreviations"),
        ("overall_description", "4. Overall Description"),
        ("functional_requirements", "5. Functional Requirements"),
        ("non_functional_requirements", "6. Non-Functional Requirements"),
        ("use_cases", "7. Use Cases"),
        ("constraints", "8. Constraints"),
    ]
    lines = [
        f"# Software Requirements Specification — {project.get('name','')}",
        "",
        f"- **Source:** {project.get('source_tech','')}",
        f"- **Target:** {project.get('target_tech','')}",
        f"- **Version:** {srs.get('version', 1)}",
        f"- **Frozen:** {srs.get('frozen', False)}  ({srs.get('frozen_at','')})",
        "",
        "---",
        "",
    ]
    for key, label in order:
        lines.append(f"## {label}\n\n{sec.get(key, '') or '_(empty)_'}\n")
    return "\n".join(lines)


@router.post("/push")
async def push_to_github(payload: GithubPushRequest):
    """Push SRS markdown to GitHub. Stage 2-4 pushes are stubbed."""
    proj = await projects.find_one({"id": payload.project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(404, "Project not found")

    repo_url = payload.repo_url or proj.get("github_repo", "")
    token = payload.token or proj.get("github_token", "")
    branch = payload.branch or proj.get("github_branch", "main")

    if not repo_url or not token:
        return {"status": "error", "message": "GitHub repo and token must be configured in Settings."}

    srs = await srs_documents.find_one({"project_id": payload.project_id}, {"_id": 0})
    if not srs:
        return {"status": "error", "message": "No SRS to push — generate and freeze the SRS first."}

    try:
        from github import Github
        owner, repo_name = _parse_repo(repo_url)
        gh = Github(token)
        repo = gh.get_repo(f"{owner}/{repo_name}")
        content = _srs_to_markdown(proj, srs)
        path = "docs/SRS.md"
        try:
            existing = repo.get_contents(path, ref=branch)
            repo.update_file(path, "LAMA: update SRS", content, existing.sha, branch=branch)
            action = "updated"
        except Exception:
            repo.create_file(path, "LAMA: add SRS", content, branch=branch)
            action = "created"
    except Exception as e:
        return {"status": "error", "message": f"GitHub push failed: {e}"}

    await audit_log.insert_one({
        "action": "github.push",
        "project_id": payload.project_id,
        "at": datetime.now(timezone.utc).isoformat(),
        "details": {"path": path, "action": action, "branch": branch},
    })

    return {
        "status": "success",
        "message": f"SRS {action} at docs/SRS.md on branch {branch}",
        "project_id": payload.project_id,
        "repo_url": repo_url,
        "branch": branch,
    }
