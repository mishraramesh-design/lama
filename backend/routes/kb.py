"""Knowledge Base endpoints: upload, build, status, scan-folder."""
import os
import re
import logging
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from typing import List
from datetime import datetime, timezone

from db import kb_files, kb_chunks, kb_entities, kb_toon, projects
from models import KBFile, KBStatus
from kb.parsers import parse_file, chunk_text
from kb.owl_extractor import extract, aggregate_stats
from kb.toon import serialise, summarise
from kb.vector_store import index_chunks as qdrant_index, delete_project_vectors

logger = logging.getLogger("lama.kb")

router = APIRouter(prefix="/kb", tags=["kb"])

ALLOWED_EXTS = {".php", ".sql", ".pdf", ".csv", ".docx", ".txt", ".md", ".zip"}
SKIP_DIRS = {"node_modules", ".git", "vendor", "__pycache__", ".idea", ".vscode", "dist", "build"}
SKIP_FILE_PATTERNS = [
    re.compile(r"\.bak$", re.IGNORECASE),
    re.compile(r"\.save$", re.IGNORECASE),
    re.compile(r"_(bkp|old|backup)", re.IGNORECASE),
    re.compile(r"\.php_", re.IGNORECASE),  # AirtelApi.php_03Mar2025
]


def _should_skip_file(name: str) -> bool:
    return any(p.search(name) for p in SKIP_FILE_PATTERNS)


@router.post("/scan-folder")
async def scan_folder(payload: dict):
    """Walk a folder on the server filesystem and ingest all supported files."""
    project_id = payload.get("project_id")
    folder = payload.get("folder_path", "").strip()
    if not project_id:
        raise HTTPException(400, "project_id required")
    if not folder:
        raise HTTPException(400, "folder_path required")

    if not os.path.isdir(folder):
        raise HTTPException(400, f"Path does not exist or is not a directory: {folder}")

    proj = await projects.find_one({"id": project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(404, "Project not found")

    processed: list[str] = []
    skipped: list[str] = []

    for root, dirs, files in os.walk(folder):
        # prune skipped directories in-place
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            full = os.path.join(root, f)
            if _should_skip_file(f):
                skipped.append(f)
                continue
            ext = os.path.splitext(f)[1].lower()
            if ext not in ALLOWED_EXTS:
                continue
            try:
                with open(full, "rb") as fh:
                    content = fh.read()
            except Exception:
                skipped.append(f)
                continue

            filetype, text = parse_file(f, content)
            chunks = chunk_text(text)

            kb_file = KBFile(
                project_id=project_id,
                filename=os.path.relpath(full, folder),
                filetype=filetype,
                size=len(content),
                chunk_count=len(chunks),
                status="uploaded",
            )
            await kb_file_persist(kb_file, project_id, text, chunks)
            processed.append(kb_file.filename)

    return {
        "ok": True,
        "scanned": len(processed),
        "skipped": len(skipped),
        "files": processed,
        "skipped_files": skipped[:50],
    }


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
        await kb_file_persist(kb_file, project_id, text, chunks)

        uploaded.append({
            "id": kb_file.id,
            "filename": kb_file.filename,
            "filetype": kb_file.filetype,
            "size": kb_file.size,
            "chunks": kb_file.chunk_count,
            "entities": kb_file.entity_count,
        })

    return {"uploaded": uploaded}


async def kb_file_persist(kb_file: KBFile, project_id: str, text: str, chunks: list[str]) -> None:
    """Persist file + chunks + run OWL extraction on the in-memory parsed text."""
    # extract entities BEFORE chunks are persisted (avoids re-joining 90k chunks later)
    entities = extract(kb_file.filetype, text, kb_file.filename)
    kb_file.entity_count = len(entities)
    kb_file.status = "processed"
    await kb_files.insert_one(kb_file.model_dump())

    # store chunks
    if chunks:
        # batch the inserts so we never hold all 90k chunk dicts at once
        BATCH = 1000
        for start in range(0, len(chunks), BATCH):
            chunk_docs = [
                {
                    "id": f"{kb_file.id}:{i}",
                    "project_id": project_id,
                    "file_id": kb_file.id,
                    "chunk_index": i,
                    "content": c,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                for i, c in enumerate(chunks[start:start + BATCH], start=start)
            ]
            await kb_chunks.insert_many(chunk_docs)

    # store entities (also batched)
    if entities:
        BATCH = 1000
        for start in range(0, len(entities), BATCH):
            docs = []
            for e in entities[start:start + BATCH]:
                e_doc = dict(e)
                e_doc["project_id"] = project_id
                e_doc["file_id"] = kb_file.id
                docs.append(e_doc)
            await kb_entities.insert_many(docs)

    await kb_files.update_one(
        {"id": kb_file.id},
        {"$set": {"raw_text_len": len(text), "entity_count": kb_file.entity_count, "status": "processed"}},
    )


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


@router.delete("/{project_id}/all")
async def delete_all_kb(project_id: str):
    """Wipe all KB data for a project (files, chunks, entities, TOON, vectors)."""
    await kb_chunks.delete_many({"project_id": project_id})
    await kb_entities.delete_many({"project_id": project_id})
    await kb_files.delete_many({"project_id": project_id})
    await kb_toon.delete_one({"project_id": project_id})
    try:
        await delete_project_vectors(project_id)
    except Exception:
        pass
    return {"ok": True}


@router.post("/build")
async def build_kb(payload: dict):
    project_id = payload.get("project_id")
    if not project_id:
        raise HTTPException(400, "project_id required")

    files = await kb_files.find({"project_id": project_id}, {"_id": 0}).to_list(2000)
    if not files:
        raise HTTPException(400, "No files uploaded")

    # Re-extract for any file that has chunks but zero entities (legacy uploads or
    # files where extraction was added after the upload).
    for f in files:
        existing = await kb_entities.count_documents({"file_id": f["id"]})
        if existing > 0:
            continue
        if f.get("filetype") not in ("php", "sql", "zip"):
            continue
        # Rebuild raw text from chunks — no cap, batched read
        cur = kb_chunks.find({"file_id": f["id"]}, {"_id": 0}).sort("chunk_index", 1)
        # Use the chunker overlap of 150 chars; for accuracy we just join — minor
        # duplicate text in overlaps is harmless for regex matching.
        pieces: list[str] = []
        async for c in cur:
            pieces.append(c["content"])
        text = "\n".join(pieces)
        try:
            entities = extract(f["filetype"], text, f["filename"])
        except Exception:
            entities = []
        if entities:
            BATCH = 1000
            for start in range(0, len(entities), BATCH):
                docs = []
                for e in entities[start:start + BATCH]:
                    e_doc = dict(e)
                    e_doc["project_id"] = project_id
                    e_doc["file_id"] = f["id"]
                    docs.append(e_doc)
                await kb_entities.insert_many(docs)
        await kb_files.update_one(
            {"id": f["id"]},
            {"$set": {"entity_count": len(entities), "status": "processed"}},
        )

    # Aggregate
    all_entities = await kb_entities.find({"project_id": project_id}, {"_id": 0}).to_list(100000)

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

    # Push all chunks into Qdrant for semantic RAG (best-effort, non-blocking failure).
    all_chunk_dicts: list[dict] = []
    for f in files:
        cur = kb_chunks.find({"file_id": f["id"]}, {"_id": 0})
        async for c in cur:
            all_chunk_dicts.append({
                "id": c["id"],
                "content": c["content"],
                "filename": f["filename"],
                "filetype": f["filetype"],
            })
    indexed = 0
    if all_chunk_dicts:
        logger.info(f"Indexing {len(all_chunk_dicts)} chunks into Qdrant")
        try:
            indexed = await qdrant_index(project_id, all_chunk_dicts)
        except Exception as e:
            logger.warning(f"Qdrant indexing failed (continuing without RAG): {e}")

    return {
        "ok": True,
        "stats": stats,
        "summary": summary,
        "toon_size": len(toon),
        "indexed": indexed,
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
