"""Knowledge Base endpoints: upload, build, status, scan-folder."""
import os
import re
import uuid
import logging
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from typing import Dict, List
from datetime import datetime, timezone

from db import kb_files, kb_chunks, kb_entities, kb_toon, projects, srs_documents, ontology_snapshots, business_ontologies
from models import KBFile, KBStatus
from kb.parsers import parse_file, chunk_text
from kb.owl_extractor import extract, aggregate_stats
from kb.toon import serialise, summarise
from kb.vector_store import index_chunks as qdrant_index, delete_project_vectors
from kb.owl_export import export_owl
from kb.module_inventory_parser import parse_module_inventory, generate_module_text_summary
from kb.business_ontology import (
    cluster_entities,
    compute_kb_hash,
    enrich_with_llm,
    compose_business_ontology,
)

logger = logging.getLogger("lama.kb")

router = APIRouter(prefix="/kb", tags=["kb"])

ALLOWED_EXTS = {
    # Core legacy
    ".php", ".sql",
    # Java stack (added)
    ".java", ".jsp", ".jspx", ".jspf", ".tag", ".tld", ".xml", ".properties", ".xhtml",
    # .NET / VB stack
    ".cs", ".vb", ".aspx", ".cshtml", ".vbhtml", ".config",
    # Frontend / scripting
    ".js", ".jsx", ".ts", ".tsx", ".html", ".htm", ".css", ".scss",
    # Python
    ".py",
    # Data / docs
    ".pdf", ".csv", ".docx", ".txt", ".md", ".yaml", ".yml", ".json",
    # Archives
    ".zip",
}
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


@router.get("/{project_id}/ontology")
async def get_ontology(project_id: str):
    """Return a nodes/edges graph of all extracted ontology elements for the
    Ontology Studio visualiser. Pure JSON — no LLM call."""
    proj = await projects.find_one({"id": project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(404, "Project not found")
    entities = await kb_entities.find({"project_id": project_id}, {"_id": 0}).to_list(100000)

    nodes: list[dict] = []
    edges: list[dict] = []
    node_ids: set[str] = set()
    type_counts: dict[str, int] = {}

    def add_node(nid: str, ntype: str, label: str, **meta):
        if nid in node_ids:
            return
        node_ids.add(nid)
        nodes.append({"id": nid, "type": ntype, "label": label, **meta})
        type_counts[ntype] = type_counts.get(ntype, 0) + 1

    def add_edge(src: str, dst: str, kind: str):
        if src in node_ids and dst in node_ids:
            edges.append({"source": src, "target": dst, "kind": kind})

    for e in entities:
        et = e.get("type", "")
        src = e.get("source", "")

        if et == "CLASS":
            cid = f"class:{e.get('namespace', '')}.{e['name']}"
            add_node(cid, "Class", e["name"],
                     namespace=e.get("namespace", ""),
                     source=src,
                     extends=e.get("extends", ""),
                     implements=e.get("implements", []),
                     is_jpa_entity=e.get("is_jpa_entity", False))
            if e.get("extends"):
                pid = f"class:{e['extends']}"
                add_node(pid, "Class", e["extends"], synthetic=True)
                add_edge(cid, pid, "extends")
            for impl in (e.get("implements") or []):
                iid = f"interface:{impl}"
                add_node(iid, "Interface", impl, synthetic=True)
                add_edge(cid, iid, "implements")
            for m in (e.get("methods") or []):
                mid = f"method:{cid}#{m['name']}"
                add_node(mid, "Method", m["name"],
                         params=m.get("params", ""), tables=m.get("tables", []),
                         sessions=m.get("sessions", []), parent_class=cid)
                add_edge(cid, mid, "has_method")
                for t in (m.get("tables") or []):
                    tid = f"table:{t}"
                    add_node(tid, "Table", t)
                    add_edge(mid, tid, "uses_table")

        elif et == "TABLE":
            tid = f"table:{e['name']}"
            add_node(tid, "Table", e["name"],
                     columns=e.get("columns", []),
                     source=src)
            for c in (e.get("columns") or []):
                cid = f"col:{e['name']}.{c.get('name', '')}"
                add_node(cid, "Column", c.get("name", ""),
                         data_type=c.get("type", ""), is_pk=c.get("is_pk", False),
                         is_fk=c.get("is_fk", False), parent_table=tid)
                add_edge(tid, cid, "has_column")
                if c.get("references"):
                    ref_tid = f"table:{c['references']}"
                    add_node(ref_tid, "Table", c["references"], synthetic=True)
                    add_edge(tid, ref_tid, "references")

        elif et == "TABLE_HINT":
            tid = f"table:{e['name']}"
            add_node(tid, "Table", e["name"], hint_from=src,
                     via=e.get("via", ""))

        elif et == "ROUTE":
            rid = f"route:{e.get('verb', '')}:{e['name']}"
            add_node(rid, "Route", e["name"],
                     verb=e.get("verb", ""), handler=e.get("handler", ""),
                     source=src)

        elif et == "JSP_FORM":
            fid = f"jspform:{e.get('action', '')}:{src}"
            add_node(fid, "JspForm", e.get("action", ""), source=src)
            # Try to link to a matching route
            for n in nodes:
                if n["type"] == "Route" and n["label"].rstrip("/") == e.get("action", "").rstrip("/"):
                    add_edge(fid, n["id"], "posts_to")
                    break

        elif et == "JSP_INCLUDE":
            iid = f"jspinclude:{e.get('file', '')}:{src}"
            add_node(iid, "JspInclude", e.get("file", ""), source=src)

        elif et == "JSP_TABLE_REFS":
            for t in (e.get("tables") or []):
                add_node(f"table:{t}", "Table", t, hint_from=src)

        elif et == "ROLE":
            rid = f"role:{e['name']}"
            add_node(rid, "Role", e["name"], source=src)

        elif et == "RELATIONSHIP":
            # Direct table-to-table FK relationship
            a = f"table:{e.get('from', '')}"
            b = f"table:{e.get('to', '')}"
            add_node(a, "Table", e.get("from", ""), synthetic=True)
            add_node(b, "Table", e.get("to", ""), synthetic=True)
            add_edge(a, b, e.get("kind", "references"))

    return {
        "project_id": project_id,
        "stats": {
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "by_type": type_counts,
        },
        "nodes": nodes,
        "edges": edges,
    }


@router.post("/{project_id}/ontology/snapshot")
async def create_ontology_snapshot(project_id: str, payload: dict = None):
    """Save the current ontology as a named snapshot (for later diff)."""
    proj = await projects.find_one({"id": project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(404, "Project not found")
    name = (payload or {}).get("name", "").strip() or f"snapshot-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
    # Re-use get_ontology aggregation
    onto = await get_ontology(project_id)
    snap_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    await ontology_snapshots.insert_one({
        "id": snap_id, "project_id": project_id, "name": name,
        "nodes": onto["nodes"], "edges": onto["edges"], "stats": onto["stats"],
        "created_at": now,
    })
    return {"snapshot_id": snap_id, "name": name, "created_at": now, "stats": onto["stats"]}


@router.get("/{project_id}/ontology/snapshots")
async def list_ontology_snapshots(project_id: str):
    rows = await ontology_snapshots.find(
        {"project_id": project_id}, {"_id": 0, "nodes": 0, "edges": 0}
    ).sort("created_at", -1).to_list(100)
    return {"snapshots": rows, "count": len(rows)}


@router.delete("/{project_id}/ontology/snapshot/{snapshot_id}")
async def delete_ontology_snapshot(project_id: str, snapshot_id: str):
    r = await ontology_snapshots.delete_one({"id": snapshot_id, "project_id": project_id})
    if r.deleted_count == 0:
        raise HTTPException(404, "Snapshot not found")
    return {"ok": True}


@router.get("/{project_id}/ontology/diff")
async def diff_ontology(project_id: str, a: str = "", b: str = "current"):
    """Diff two ontology states.
    - `a` is a snapshot_id (required)
    - `b` is either another snapshot_id or the literal "current" (default)
    Returns added / removed / unchanged nodes and edges.
    """
    if not a:
        raise HTTPException(400, "query param 'a' (snapshot_id) is required")
    snap_a = await ontology_snapshots.find_one({"id": a, "project_id": project_id}, {"_id": 0})
    if not snap_a:
        raise HTTPException(404, "Snapshot A not found")
    if b == "current":
        snap_b = await get_ontology(project_id)
        snap_b_name = "Current"
    else:
        snap_b = await ontology_snapshots.find_one({"id": b, "project_id": project_id}, {"_id": 0})
        if not snap_b:
            raise HTTPException(404, "Snapshot B not found")
        snap_b_name = snap_b.get("name", "")

    a_node_ids = {n["id"] for n in snap_a.get("nodes", [])}
    b_node_ids = {n["id"] for n in snap_b.get("nodes", [])}
    a_edges = {(e["source"], e["target"], e.get("kind", "")) for e in snap_a.get("edges", [])}
    b_edges = {(e["source"], e["target"], e.get("kind", "")) for e in snap_b.get("edges", [])}

    added_nodes = [n for n in snap_b.get("nodes", []) if n["id"] not in a_node_ids]
    removed_nodes = [n for n in snap_a.get("nodes", []) if n["id"] not in b_node_ids]
    unchanged_node_ids = a_node_ids & b_node_ids

    added_edges = [{"source": s, "target": t, "kind": k} for (s, t, k) in (b_edges - a_edges)]
    removed_edges = [{"source": s, "target": t, "kind": k} for (s, t, k) in (a_edges - b_edges)]

    by_type_delta: Dict[str, int] = {}
    for n in added_nodes:
        by_type_delta[n["type"]] = by_type_delta.get(n["type"], 0) + 1
    for n in removed_nodes:
        by_type_delta[n["type"]] = by_type_delta.get(n["type"], 0) - 1

    return {
        "a": {"id": a, "name": snap_a.get("name", ""), "created_at": snap_a.get("created_at", "")},
        "b": {"id": b, "name": snap_b_name, "created_at": snap_b.get("created_at", "")},
        "summary": {
            "added_nodes": len(added_nodes), "removed_nodes": len(removed_nodes),
            "unchanged_nodes": len(unchanged_node_ids),
            "added_edges": len(added_edges), "removed_edges": len(removed_edges),
            "by_type_delta": by_type_delta,
        },
        "added_nodes": added_nodes, "removed_nodes": removed_nodes,
        "added_edges": added_edges, "removed_edges": removed_edges,
    }


# ─────────────────────────────────────────────────────────────────────────
# Business-Domain Ontology (deterministic clustering + LLM enrichment).
# Replaces the raw code-level Class/Table/Column graph for users who want
# to see real-world concepts (Citizen, Loan Application, Invoice, …).
# ─────────────────────────────────────────────────────────────────────────
import asyncio
import time as _time
from typing import Any as _Any

_BIZ_JOBS: Dict[str, Dict[str, _Any]] = {}
_BIZ_JOB_TTL = 60 * 30  # 30 minutes


def _biz_gc():
    now = _time.time()
    for k in [k for k, v in _BIZ_JOBS.items() if v.get("ended_at") and now - v["ended_at"] > _BIZ_JOB_TTL]:
        _BIZ_JOBS.pop(k, None)


async def _build_business_ontology(project_id: str, force: bool = False) -> dict:
    proj = await projects.find_one({"id": project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(404, "Project not found")
    entities = await kb_entities.find({"project_id": project_id}, {"_id": 0}).to_list(100000)
    if not entities:
        raise HTTPException(400, "KB is empty — upload files and build the KB first.")

    kb_hash = compute_kb_hash(entities)
    cached = await business_ontologies.find_one({"project_id": project_id}, {"_id": 0})
    if cached and not force and cached.get("kb_hash") == kb_hash and cached.get("payload"):
        return {**cached["payload"], "cached": True, "kb_hash": kb_hash,
                "generated_at": cached.get("generated_at")}

    clusters_pack = cluster_entities(entities)
    llm_result = await enrich_with_llm(clusters_pack, proj, project_id)
    payload = compose_business_ontology(clusters_pack, llm_result)

    now = datetime.now(timezone.utc).isoformat()
    await business_ontologies.update_one(
        {"project_id": project_id},
        {"$set": {
            "project_id": project_id,
            "kb_hash": kb_hash,
            "payload": payload,
            "generated_at": now,
            "source": payload.get("source"),
        }},
        upsert=True,
    )
    return {**payload, "cached": False, "kb_hash": kb_hash, "generated_at": now}


async def _biz_run(project_id: str, job_id: str, force: bool):
    try:
        _BIZ_JOBS[job_id]["status"] = "running"
        result = await _build_business_ontology(project_id, force=force)
        _BIZ_JOBS[job_id].update({
            "status": "done",
            "result": result,
            "ended_at": _time.time(),
            "progress": 1.0,
        })
    except Exception as exc:
        _BIZ_JOBS[job_id].update({
            "status": "error",
            "error": str(exc)[:500],
            "ended_at": _time.time(),
        })


@router.get("/{project_id}/business-ontology")
async def get_business_ontology(project_id: str):
    """Return the cached business-domain ontology for the project.
    Returns 404 if it has never been generated — call jobs/start first."""
    cached = await business_ontologies.find_one({"project_id": project_id}, {"_id": 0})
    if not cached or not cached.get("payload"):
        raise HTTPException(404, "No business ontology cached yet — call /business-ontology/jobs/start")
    # Compare hash against current KB to surface staleness
    entities = await kb_entities.find({"project_id": project_id}, {"_id": 0}).to_list(100000)
    current_hash = compute_kb_hash(entities) if entities else ""
    stale = bool(current_hash and current_hash != cached.get("kb_hash"))
    return {
        **cached["payload"],
        "cached": True,
        "kb_hash": cached.get("kb_hash"),
        "current_kb_hash": current_hash,
        "stale": stale,
        "generated_at": cached.get("generated_at"),
    }


@router.post("/{project_id}/business-ontology/jobs/start")
async def start_business_ontology_job(project_id: str, payload: dict | None = None):
    """Kick off a background build of the business ontology. Returns a job_id
    the client can poll. If a fresh cached copy exists and `force` is false,
    returns the cached result immediately under `result` instead."""
    force = bool((payload or {}).get("force", False))
    _biz_gc()

    proj = await projects.find_one({"id": project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(404, "Project not found")
    entities_count = await kb_entities.count_documents({"project_id": project_id})
    if entities_count == 0:
        raise HTTPException(400, "KB is empty — upload files and build the KB first.")

    # If we already have a fresh cache, skip the job entirely.
    if not force:
        entities = await kb_entities.find({"project_id": project_id}, {"_id": 0}).to_list(100000)
        current_hash = compute_kb_hash(entities)
        cached = await business_ontologies.find_one({"project_id": project_id}, {"_id": 0})
        if cached and cached.get("kb_hash") == current_hash and cached.get("payload"):
            jid = uuid.uuid4().hex
            _BIZ_JOBS[jid] = {
                "id": jid, "project_id": project_id, "status": "done",
                "started_at": _time.time(), "ended_at": _time.time(),
                "progress": 1.0,
                "result": {**cached["payload"], "cached": True,
                           "kb_hash": current_hash, "generated_at": cached.get("generated_at")},
            }
            return {"job_id": jid, "status": "done", "cached": True}

    jid = uuid.uuid4().hex
    _BIZ_JOBS[jid] = {
        "id": jid, "project_id": project_id, "status": "queued",
        "started_at": _time.time(), "progress": 0.05,
    }
    asyncio.create_task(_biz_run(project_id, jid, force=force))
    return {"job_id": jid, "status": "queued", "cached": False}


@router.get("/{project_id}/business-ontology/jobs/{job_id}")
async def get_business_ontology_job(project_id: str, job_id: str):
    j = _BIZ_JOBS.get(job_id)
    if not j or j.get("project_id") != project_id:
        raise HTTPException(404, "Job not found (or expired)")
    return {
        "job_id": job_id,
        "status": j.get("status"),
        "progress": j.get("progress", 0.0),
        "error": j.get("error"),
        "result": j.get("result"),
    }


@router.post("/{project_id}/business-ontology/regenerate")
async def regenerate_business_ontology(project_id: str):
    """Force a fresh deterministic + LLM run (sync). Prefer jobs/start for big KBs."""
    return await _build_business_ontology(project_id, force=True)


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
