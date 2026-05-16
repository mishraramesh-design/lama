"""SRS generation, retrieval, freeze, section edit."""
import json
import io
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from datetime import datetime, timezone

from db import srs_documents, kb_toon, messages, projects, audit_log, prompts, project_prompts
from models import SRSDocument, SRSSectionUpdate
from llm import chat_completion

router = APIRouter(prefix="/srs", tags=["srs"])

DEFAULT_SECTIONS = [
    "1. Purpose",
    "2. Scope",
    "3. Definitions, Acronyms, Abbreviations",
    "4. Overall Description",
    "5. Functional Requirements",
    "6. Non-Functional Requirements",
    "7. Use Cases",
    "8. Constraints",
]


async def _get_prompt(project_id: str, key: str) -> str:
    p = await project_prompts.find_one({"project_id": project_id, "key": key}, {"_id": 0})
    if p:
        return p["template"]
    g = await prompts.find_one({"key": key}, {"_id": 0})
    return g["template"] if g else ""


@router.post("/generate")
async def generate_srs(payload: dict):
    project_id = payload.get("project_id")
    conversation_id = payload.get("conversation_id")
    model = payload.get("model") or "deepseek/deepseek-chat"

    proj = await projects.find_one({"id": project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(404, "Project not found")

    toon_doc = await kb_toon.find_one({"project_id": project_id}, {"_id": 0})
    toon_context = (toon_doc or {}).get("toon", "")[:10000]

    q = {"project_id": project_id}
    if conversation_id:
        q["conversation_id"] = conversation_id
    history = await messages.find(q, {"_id": 0}).sort("created_at", 1).to_list(200)
    convo_text = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in history)[-8000:]

    template = await _get_prompt(project_id, "srs.generate")
    if not template:
        template = (
            "You are an IEEE 830 SRS analyst. Given this TOON knowledge base:\n{toon_context}\n"
            "and this conversation history:\n{conversation}\n"
            "Generate a complete SRS with sections:\n"
            "1-Purpose 2-Scope 3-Definitions 4-Overall Description 5-Functional Requirements "
            "6-Non-Functional Requirements 7-Use Cases 8-Constraints.\n"
            "Be specific. Use actual entity names from the KB. Do not hallucinate features.\n"
            "Return strict JSON with keys exactly: purpose, scope, definitions, overall_description, "
            "functional_requirements, non_functional_requirements, use_cases, constraints. "
            "Each value is markdown text."
        )

    system_content = template.format(
        toon_context=toon_context,
        conversation=convo_text,
    )
    system_content += "\n\nReturn ONLY valid JSON, no preamble, no code fences."

    llm_messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": "Generate the SRS document now."},
    ]

    try:
        result = await chat_completion(messages=llm_messages, model=model, temperature=0.2, max_tokens=6000)
    except Exception as e:
        raise HTTPException(502, f"LLM call failed: {e}")

    raw = result["content"].strip()
    # try to extract JSON
    sections = _parse_srs_json(raw)

    # store
    now = datetime.now(timezone.utc).isoformat()
    existing = await srs_documents.find_one({"project_id": project_id}, {"_id": 0})
    if existing and existing.get("frozen"):
        raise HTTPException(400, "SRS is frozen — unfreeze before regenerating")

    doc = SRSDocument(
        project_id=project_id,
        sections=sections,
        version=(existing.get("version", 0) + 1) if existing else 1,
    )
    doc_dict = doc.model_dump()
    doc_dict["updated_at"] = now

    await srs_documents.update_one(
        {"project_id": project_id},
        {"$set": doc_dict},
        upsert=True,
    )

    await audit_log.insert_one({
        "action": "srs.generate",
        "project_id": project_id,
        "at": now,
        "details": {"model": result["model"], "tokens": result["usage"].get("total_tokens", 0)},
    })

    return {
        "ok": True,
        "sections": sections,
        "usage": result["usage"],
        "version": doc_dict["version"],
    }


def _parse_srs_json(raw: str) -> dict:
    """Robust JSON parse with fallbacks."""
    text = raw.strip()
    # strip code fences
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    # try direct
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return _normalise_keys(data)
    except Exception:
        pass
    # find first { ... last }
    s = text.find("{")
    e = text.rfind("}")
    if s >= 0 and e > s:
        try:
            data = json.loads(text[s:e + 1])
            return _normalise_keys(data)
        except Exception:
            pass
    # fallback: put raw under purpose
    return {
        "purpose": raw,
        "scope": "",
        "definitions": "",
        "overall_description": "",
        "functional_requirements": "",
        "non_functional_requirements": "",
        "use_cases": "",
        "constraints": "",
    }


def _normalise_keys(d: dict) -> dict:
    out = {
        "purpose": "",
        "scope": "",
        "definitions": "",
        "overall_description": "",
        "functional_requirements": "",
        "non_functional_requirements": "",
        "use_cases": "",
        "constraints": "",
    }
    for k, v in d.items():
        key = k.lower().replace(" ", "_").replace("-", "_")
        if key in out:
            out[key] = v if isinstance(v, str) else json.dumps(v, indent=2)
    return out


@router.get("/{project_id}")
async def get_srs(project_id: str):
    doc = await srs_documents.find_one({"project_id": project_id}, {"_id": 0})
    if not doc:
        return {
            "project_id": project_id,
            "sections": {k: "" for k in [
                "purpose", "scope", "definitions", "overall_description",
                "functional_requirements", "non_functional_requirements",
                "use_cases", "constraints",
            ]},
            "frozen": False,
            "version": 0,
        }
    return doc


@router.put("/{project_id}/section")
async def update_section(project_id: str, payload: SRSSectionUpdate):
    doc = await srs_documents.find_one({"project_id": project_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "SRS not found — generate first")
    if doc.get("frozen"):
        raise HTTPException(400, "SRS is frozen")
    await srs_documents.update_one(
        {"project_id": project_id},
        {"$set": {
            f"sections.{payload.section}": payload.content,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    return {"ok": True}


@router.post("/freeze")
async def freeze_srs(payload: dict):
    project_id = payload.get("project_id")
    user = payload.get("user", "system")
    doc = await srs_documents.find_one({"project_id": project_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "SRS not found")
    now = datetime.now(timezone.utc).isoformat()
    await srs_documents.update_one(
        {"project_id": project_id},
        {"$set": {"frozen": True, "frozen_at": now, "frozen_by": user, "updated_at": now}},
    )
    await projects.update_one(
        {"id": project_id},
        {"$set": {
            "stage_status.Discovery": "frozen",
            "freeze_gates.Discovery": {"at": now, "by": user},
            "updated_at": now,
        }},
    )
    await audit_log.insert_one({
        "action": "srs.freeze",
        "project_id": project_id,
        "at": now,
        "details": {"by": user},
    })
    return {"ok": True, "frozen_at": now}


@router.post("/unfreeze")
async def unfreeze_srs(payload: dict):
    project_id = payload.get("project_id")
    now = datetime.now(timezone.utc).isoformat()
    await srs_documents.update_one(
        {"project_id": project_id},
        {"$set": {"frozen": False, "updated_at": now}},
    )
    await projects.update_one(
        {"id": project_id},
        {"$set": {"stage_status.Discovery": "active", "updated_at": now}},
    )
    return {"ok": True}


@router.get("/{project_id}/export.pdf")
async def export_pdf(project_id: str):
    doc = await srs_documents.find_one({"project_id": project_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "SRS not found")
    proj = await projects.find_one({"id": project_id}, {"_id": 0})
    pdf_bytes = _render_pdf(proj, doc)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="SRS_{proj.get("name","project")}.pdf"'},
    )


def _render_pdf(project: dict, doc: dict) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
    from reportlab.lib.units import cm

    buf = io.BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("title", parent=styles["Title"], fontSize=20, spaceAfter=20)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=14, spaceBefore=14, spaceAfter=8)
    body = ParagraphStyle("body", parent=styles["BodyText"], fontSize=10.5, leading=15)

    elements = []
    elements.append(Paragraph("Software Requirements Specification", title_style))
    elements.append(Paragraph(f"<b>Project:</b> {project.get('name','')}", body))
    elements.append(Paragraph(f"<b>Source:</b> {project.get('source_tech','')}  →  <b>Target:</b> {project.get('target_tech','')}", body))
    elements.append(Paragraph(f"<b>Version:</b> {doc.get('version',1)} | <b>Frozen:</b> {doc.get('frozen', False)}", body))
    elements.append(Spacer(1, 12))

    section_order = [
        ("purpose", "1. Purpose"),
        ("scope", "2. Scope"),
        ("definitions", "3. Definitions, Acronyms & Abbreviations"),
        ("overall_description", "4. Overall Description"),
        ("functional_requirements", "5. Functional Requirements"),
        ("non_functional_requirements", "6. Non-Functional Requirements"),
        ("use_cases", "7. Use Cases"),
        ("constraints", "8. Constraints"),
    ]
    sections = doc.get("sections", {})
    for key, label in section_order:
        elements.append(Paragraph(label, h2))
        text = (sections.get(key) or "(empty)").replace("\n", "<br/>")
        elements.append(Paragraph(text, body))

    pdf.build(elements)
    return buf.getvalue()
