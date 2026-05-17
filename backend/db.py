"""MongoDB connection and collection accessors."""
import os
from motor.motor_asyncio import AsyncIOMotorClient

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Collections
projects = db.projects
kb_files = db.kb_files
kb_chunks = db.kb_chunks
kb_entities = db.kb_entities
kb_toon = db.kb_toon
conversations = db.conversations
messages = db.messages
srs_documents = db.srs_documents
prompts = db.prompts
project_prompts = db.project_prompts
freeze_gates = db.freeze_gates
audit_log = db.audit_log
stage_context = db.stage_context

# Stage 2 — Data Model
data_models = db.data_models
bus_matrix = db.bus_matrix
olap_models = db.olap_models
migration_artifacts = db.migration_artifacts

# Stage 3 — Architecture
arch_documents = db.arch_documents
arch_services = db.arch_services

# Stage 4 — Code Generation
codegen_files = db.codegen_files
codegen_runs = db.codegen_runs

# Console — Model Fabric / Agent Fabric / Usage Logs
model_providers = db.model_providers
agent_configs = db.agent_configs
token_usage_log = db.token_usage_log

# GitHub configs (also referenced in routes/codegen.py)
github_configs = db.github_configs
