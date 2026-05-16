"""Knowledge Base endpoints: upload, build, status."""
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from typing import List
from datetime import datetime, timezone

from db import kb_files, kb_chunks, kb_entities, kb_toon, projects
from models import KBFile, KBStatus
from kb.parsers import parse_file, chunk_text
from kb.owl_extractor import extract, aggregate_stats
from kb.toon import serialise, summarise

router = APIRouter(prefix="/kb", tags=["kb"])


@router.post("/upload")
async def upload_files(project_id: str = Form(...), files: List[UploadFile] = File(...)):
    proj = await projects.find_one({"id": project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(404, "Project not found")

    uploaded = []
    for f in files:
        content = await f.read()
        filetype, text = parse_file(f.filename, content)
        chunks = chunk_text(text)

        kb_file = KBFile(
            project_id=project_id,
            filename=f.filename,
            filetype=filetype,
            size=len(content),
            chunk_count=len(chunks),
            status="uploaded",
        )
        await kb_files.insert_one(kb_file.model_dump())

        # store chunks
        if chunks:
            chunk_docs = [
                {
                    "id": f"{kb_file.id}:{i}",
                    "project_id": project_id,
                    "file_id": kb_file.id,
                    "chunk_index": i,
                    "content": c,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                for i, c in enumerate(chunks)
            ]
            await kb_chunks.insert_many(chunk_docs)

        # store raw text reference for OWL extraction (cache)
        await kb_files.update_one(
            {"id": kb_file.id},
            {"$set": {"raw_text_len": len(text)}}
        )

        uploaded.append({
            "id": kb_file.id,
            "filename": kb_file.filename,
            "filetype": kb_file.filetype,
            "size": kb_file.size,
            "chunks": kb_file.chunk_count,
        })

    return {"uploaded": uploaded}


@router.get("/{project_id}/files")
async def list_files(project_id: str):
    docs = await kb_files.find({"project_id": project_id}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return docs


@router.delete("/files/{file_id}")
async def delete_file(file_id: str):
    f = await kb_files.find_one({"id": file_id}, {"_id": 0})
    if not f:
        raise HTTPException(404, "File not found")
    await kb_chunks.delete_many({"file_id": file_id})
    await kb_entities.delete_many({"file_id": file_id})
    await kb_files.delete_one({"id": file_id})
    return {"ok": True}


@router.post("/build")
async def build_kb(payload: dict):
    project_id = payload.get("project_id")
    if not project_id:
        raise HTTPException(400, "project_id required")

    files = await kb_files.find({"project_id": project_id}, {"_id": 0}).to_list(500)
    if not files:
        raise HTTPException(400, "No files uploaded")

    # Clear previous extracted entities for this project
    await kb_entities.delete_many({"project_id": project_id})

    all_entities = []
    for f in files:
        # Re-read text from chunks (joined)
        chunks_cur = kb_chunks.find({"file_id": f["id"]}, {"_id": 0}).sort("chunk_index", 1)
        chunks = await chunks_cur.to_list(10000)
        text = "\n".join(c["content"] for c in chunks)
        entities = extract(f["filetype"], text, f["filename"])

        if entities:
            docs = []
            for e in entities:
                e_doc = dict(e)
                e_doc["project_id"] = project_id
                e_doc["file_id"] = f["id"]
                docs.append(e_doc)
            await kb_entities.insert_many(docs)
            all_entities.extend(entities)

        await kb_files.update_one(
            {"id": f["id"]},
            {"$set": {"entity_count": len(entities), "status": "processed"}}
        )

    toon = serialise(all_entities)
    stats = aggregate_stats(all_entities)
    summary = summarise(all_entities, stats)

    await kb_toon.update_one(
        {"project_id": project_id},
        {"$set": {
            "project_id": project_id,
            "toon": toon,
            "summary": summary,
            "stats": stats,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )

    return {
        "ok": True,
        "stats": stats,
        "summary": summary,
        "toon_size": len(toon),
    }


@router.get("/{project_id}/status", response_model=KBStatus)
async def kb_status(project_id: str):
    file_count = await kb_files.count_documents({"project_id": project_id})
    chunk_count = await kb_chunks.count_documents({"project_id": project_id})
    toon_doc = await kb_toon.find_one({"project_id": project_id}, {"_id": 0})

    stats = (toon_doc or {}).get("stats", {})
    toon_size = len((toon_doc or {}).get("toon", "")) if toon_doc else 0

    return KBStatus(
        project_id=project_id,
        files=file_count,
        chunks=chunk_count,
        entities=stats.get("entities", 0),
        classes=stats.get("classes", 0),
        methods=stats.get("methods", 0),
        tables=stats.get("tables", 0),
        columns=stats.get("columns", 0),
        roles=stats.get("roles", 0),
        relationships=stats.get("relationships", 0),
        toon_size=toon_size,
    )


@router.get("/{project_id}/toon")
async def get_toon(project_id: str):
    doc = await kb_toon.find_one({"project_id": project_id}, {"_id": 0})
    if not doc:
        return {"toon": "", "summary": "", "stats": {}}
    return doc


@router.get("/{project_id}/glossary")
async def get_glossary(project_id: str):
    """Return key terms for type-ahead suggestions."""
    entities = await kb_entities.find({"project_id": project_id}, {"_id": 0}).to_list(2000)
    terms = set()
    for e in entities:
        if e.get("name"):
            terms.add(e["name"])
        for m in (e.get("methods") or []):
            if m.get("name"):
                terms.add(m["name"])
        for c in (e.get("columns") or []):
            if c.get("name"):
                terms.add(c["name"])
    return {"terms": sorted(terms)[:500]}
