"""Knowledge Base endpoints: upload, build, status, scan-folder."""
import os
import re
import logging
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from typing import List
from datetime import datetime, timezone

from db import kb_files, kb_chunks, kb_entities, kb_toon, projects, srs_documents
from models import KBFile, KBStatus
from kb.parsers import parse_file, chunk_text
from kb.owl_extractor import extract, aggregate_stats
from kb.toon import serialise, summarise
from kb.vector_store import index_chunks as qdrant_index, delete_project_vectors
from kb.owl_export import export_owl
from kb.module_inventory_parser import parse_module_inventory, generate_module_text_summary

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
        modules=stats.get("modules", 0),
        component_maps=stats.get("component_maps", 0),
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


@router.get("/{project_id}/owl-export")
async def download_owl(project_id: str):
    """Download the full OWL/JSON-LD context bundle for Stage 2 / Stage 3 consumption."""
    from fastapi.responses import JSONResponse

    proj = await projects.find_one({"id": project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(404, "Project not found")

    entities = await kb_entities.find(
        {"project_id": project_id}, {"_id": 0}
    ).to_list(100000)

    srs_doc      = await srs_documents.find_one(
        {"project_id": project_id}, {"_id": 0}
    )
    srs_sections = (srs_doc or {}).get("sections", {})

    owl_data = export_owl(proj, entities, srs_sections)

    return JSONResponse(
        content=owl_data,
        headers={
            "Content-Disposition":
                f'attachment; filename="owl_context_{project_id}.json"',
            "Content-Type": "application/json",
        },
    )



# ============================================================
# Module Inventory — generic import (Excel / CSV / JSON)
# ============================================================
@router.post("/import-module-inventory")
async def import_module_inventory(
    project_id: str = Form(...),
    file: UploadFile = File(...),
):
    """Import module inventory from .xlsx / .csv / .json. Idempotent — replaces previous MODULE/COMPONENT_MAP entities."""
    proj = await projects.find_one({"id": project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(404, "Project not found")

    fname = file.filename or "inventory"
    ext = fname.lower().rsplit(".", 1)[-1] if "." in fname else ""
    if ext not in ("xlsx", "xls", "csv", "json"):
        raise HTTPException(400, "Supported formats: .xlsx, .csv, .json")

    content = await file.read()
    entities = parse_module_inventory(fname, content)
    if not entities:
        raise HTTPException(
            422,
            "Could not parse the file. Ensure it contains module and component/table mapping data. "
            "Supported formats: Excel (.xlsx), CSV (.csv), JSON (.json).",
        )

    modules = [e for e in entities if e.get("type") == "MODULE"]
    comp_maps = [e for e in entities if e.get("type") == "COMPONENT_MAP"]
    now = datetime.now(timezone.utc).isoformat()

    # Idempotent replace
    await kb_entities.delete_many({
        "project_id": project_id,
        "type": {"$in": ["MODULE", "COMPONENT_MAP"]},
    })

    BATCH = 500
    for start in range(0, len(entities), BATCH):
        batch = entities[start:start + BATCH]
        docs = [{**e, "project_id": project_id, "file_id": "module_inventory"} for e in batch]
        if docs:
            await kb_entities.insert_many(docs)

    summary_text = generate_module_text_summary(entities)
    chunks = chunk_text(summary_text) if summary_text else []

    # Replace previous module_inventory file + chunks
    await kb_files.delete_many({"project_id": project_id, "filetype": "module_inventory"})
    await kb_chunks.delete_many({"project_id": project_id, "file_id": "module_inventory"})

    kb_file = KBFile(
        project_id=project_id,
        filename=fname,
        filetype="module_inventory",
        size=len(content),
        chunk_count=len(chunks),
        entity_count=len(entities),
        status="processed",
    )
    await kb_files.insert_one(kb_file.model_dump())

    if chunks:
        chunk_docs = [
            {
                "id": f"module_inventory:{i}",
                "project_id": project_id,
                "file_id": "module_inventory",
                "chunk_index": i,
                "content": c,
                "created_at": now,
            }
            for i, c in enumerate(chunks)
        ]
        await kb_chunks.insert_many(chunk_docs)
        try:
            await qdrant_index(project_id, [
                {
                    "id": f"module_inventory:{i}",
                    "content": c,
                    "filename": fname,
                    "filetype": "module_inventory",
                }
                for i, c in enumerate(chunks)
            ])
        except Exception:
            pass  # non-blocking

    # Rebuild TOON to include the # MODULES section
    all_entities = await kb_entities.find({"project_id": project_id}, {"_id": 0}).to_list(200000)
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
            "updated_at": now,
        }},
        upsert=True,
    )

    return {
        "ok": True,
        "modules": len(modules),
        "component_maps": len(comp_maps),
        "chunks": len(chunks),
        "format_detected": ext,
        "message": (
            f"Imported {len(modules)} modules and {len(comp_maps)} component mappings "
            f"from {ext.upper()} file. TOON rebuilt."
        ),
    }


@router.get("/{project_id}/module-traceability")
async def get_module_traceability(project_id: str):
    """Return two views: user-imported modules vs. auto-detected domain groupings."""
    from collections import defaultdict

    entities = await kb_entities.find({"project_id": project_id}, {"_id": 0}).to_list(200000)

    user_modules = [
        {
            "name": e["name"],
            "component_count": e.get("component_count", 0),
            "table_ref_count": e.get("table_ref_count", 0),
            "source_format": e.get("source_format", ""),
            "tables": (e.get("tables") or [])[:15],
            "description": e.get("description", ""),
        }
        for e in entities if e.get("type") == "MODULE"
    ]
    user_modules.sort(key=lambda x: x["table_ref_count"], reverse=True)

    auto_domains: dict = defaultdict(lambda: {"classes": [], "tables": [], "count": 0})
    for e in entities:
        if e.get("type") == "CLASS":
            touched = set()
            for m in (e.get("methods") or []):
                for t in (m.get("tables") or []):
                    p = t.split("_")
                    if len(p) > 1:
                        touched.add(p[0])
            domain = next(iter(touched), "core") if touched else "core"
            auto_domains[domain]["classes"].append(e["name"])
            auto_domains[domain]["count"] += 1
        elif e.get("type") == "TABLE":
            p = e["name"].split("_")
            domain = p[0] if len(p) > 1 else "other"
            auto_domains[domain]["tables"].append(e["name"])

    auto_list = sorted(
        [
            {
                "domain": k,
                "class_count": len(v["classes"]),
                "table_count": len(v["tables"]),
                "sample_classes": v["classes"][:5],
                "sample_tables": v["tables"][:5],
            }
            for k, v in auto_domains.items()
            if len(v["classes"]) + len(v["tables"]) > 1
        ],
        key=lambda x: x["class_count"] + x["table_count"],
        reverse=True,
    )

    return {
        "user_modules": user_modules,
        "auto_modules": auto_list,
        "has_user_import": len(user_modules) > 0,
    }
