"""Chat endpoint — uses TOON context + active prompt library."""
from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone
import uuid

from db import conversations, messages, kb_toon, prompts, project_prompts, projects
from models import ChatRequest, ChatMessage
from llm import chat_completion, estimate_tokens, AVAILABLE_MODELS

router = APIRouter(prefix="/chat", tags=["chat"])


async def _get_prompt(project_id: str, key: str) -> str:
    """Fetch effective prompt (project override -> global)."""
    p = await project_prompts.find_one({"project_id": project_id, "key": key}, {"_id": 0})
    if p:
        return p["template"]
    g = await prompts.find_one({"key": key}, {"_id": 0})
    return g["template"] if g else ""


@router.get("/models")
async def list_models():
    return {"models": AVAILABLE_MODELS}


@router.get("/{project_id}/history")
async def get_history(project_id: str, conversation_id: str | None = None):
    q = {"project_id": project_id}
    if conversation_id:
        q["conversation_id"] = conversation_id
    docs = await messages.find(q, {"_id": 0}).sort("created_at", 1).to_list(2000)
    return docs


@router.post("")
async def send_message(req: ChatRequest):
    proj = await projects.find_one({"id": req.project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(404, "Project not found")

    conversation_id = req.conversation_id or str(uuid.uuid4())

    # Load TOON context
    toon_doc = await kb_toon.find_one({"project_id": req.project_id}, {"_id": 0})
    toon_context = (toon_doc or {}).get("toon", "")
    summary = (toon_doc or {}).get("summary", "Knowledge base is empty.")

    # Load conversation history (last 20 messages)
    history = await messages.find(
        {"conversation_id": conversation_id},
        {"_id": 0},
    ).sort("created_at", 1).to_list(40)

    # Resolve prompt for the stage
    stage = (req.stage or "Discovery").lower()
    prompt_key = "srs.gap_question" if stage == "discovery" else f"{stage}.system"
    system_template = await _get_prompt(req.project_id, prompt_key)
    if not system_template:
        system_template = (
            "You are a legacy migration analyst for project {project_name}.\n"
            "Knowledge base summary: {summary}\n"
            "Use the structured knowledge base (TOON) below to ground your answers.\n"
            "{toon_context}"
        )

    asked_questions = "\n".join(
        f"- {m['content']}" for m in history if m["role"] == "assistant"
    )[-2000:]

    system_message = system_template.format(
        project_name=proj.get("name", ""),
        summary=summary,
        toon_context=toon_context[:8000],
        conversation="",
        asked_questions=asked_questions or "(none yet)",
    )

    # Save user message
    user_msg = ChatMessage(
        conversation_id=conversation_id,
        project_id=req.project_id,
        role="user",
        content=req.message,
        tokens=estimate_tokens(req.message),
    )
    await messages.insert_one(user_msg.model_dump())

    # Build LLM message list
    llm_messages = [{"role": "system", "content": system_message}]
    for m in history:
        if m["role"] in ("user", "assistant"):
            llm_messages.append({"role": m["role"], "content": m["content"]})
    llm_messages.append({"role": "user", "content": req.message})

    try:
        result = await chat_completion(messages=llm_messages, model=req.model)
    except Exception as e:
        raise HTTPException(502, f"LLM call failed: {e}")

    # Save assistant message
    assistant_msg = ChatMessage(
        conversation_id=conversation_id,
        project_id=req.project_id,
        role="assistant",
        content=result["content"],
        model=result["model"],
        tokens=result["usage"]["total_tokens"] or estimate_tokens(result["content"]),
    )
    await messages.insert_one(assistant_msg.model_dump())

    # Ensure conversation record
    await conversations.update_one(
        {"id": conversation_id},
        {"$set": {
            "id": conversation_id,
            "project_id": req.project_id,
            "stage": req.stage,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )

    return {
        "conversation_id": conversation_id,
        "message": assistant_msg.model_dump(),
        "usage": result["usage"],
    }
