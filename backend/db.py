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
