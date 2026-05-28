"""LAMA — Legacy Application Modernisation AI Studio — FastAPI entrypoint."""
from fastapi import FastAPI, APIRouter
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from pathlib import Path
import os
import logging

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

# Import after dotenv is loaded
from db import client  # noqa: E402
from routes.projects import router as projects_router  # noqa: E402
from routes.kb import router as kb_router  # noqa: E402
from routes.chat import router as chat_router  # noqa: E402
from routes.srs import router as srs_router  # noqa: E402
from routes.prompts import router as prompts_router  # noqa: E402
from routes.github import router as github_router  # noqa: E402
from routes.audit import router as audit_router  # noqa: E402
from routes.datamodel import router as datamodel_router, factory_router as factory_router  # noqa: E402
from routes.architecture import router as architecture_router  # noqa: E402
from routes.codegen import router as codegen_router  # noqa: E402
from routes.living import router as living_router  # noqa: E402
from routes.console import router as console_router  # noqa: E402
from seed import run_seed  # noqa: E402


app = FastAPI(title="LAMA API", version="0.2.0")
api_router = APIRouter(prefix="/api")


@api_router.get("/")
async def root():
    return {"service": "LAMA", "status": "ok"}


@api_router.get("/health")
async def health():
    return {"ok": True}


# Register sub-routers under /api
api_router.include_router(projects_router)
api_router.include_router(kb_router)
api_router.include_router(chat_router)
api_router.include_router(srs_router)
api_router.include_router(prompts_router)
api_router.include_router(github_router)
api_router.include_router(audit_router)
api_router.include_router(datamodel_router)
api_router.include_router(factory_router)
api_router.include_router(architecture_router)
api_router.include_router(codegen_router)
api_router.include_router(living_router)
api_router.include_router(console_router)

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("lama")


@app.on_event("startup")
async def on_startup():
    try:
        await run_seed()
        logger.info("Seed complete")
    except Exception as e:
        logger.exception(f"Seed failed: {e}")


@app.on_event("shutdown")
async def on_shutdown():
    client.close()
