import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

const api = axios.create({ baseURL: API, timeout: 600000 });

// Projects
export const listProjects = () => api.get("/projects").then((r) => r.data);
export const getProject = (id) => api.get(`/projects/${id}`).then((r) => r.data);
export const getPipelineStatus = (projectId) =>
  api.get(`/projects/${projectId}/pipeline`).then((r) => r.data);

// KB
export const scanFolder = (projectId, folderPath) =>
  api.post("/kb/scan-folder", { project_id: projectId, folder_path: folderPath }).then((r) => r.data);
export const uploadKBFiles = (projectId, files) => {
  const fd = new FormData();
  fd.append("project_id", projectId);
  files.forEach((f) => fd.append("files", f));
  return api.post("/kb/upload", fd, { headers: { "Content-Type": "multipart/form-data" } }).then((r) => r.data);
};
export const listKBFiles = (projectId) => api.get(`/kb/${projectId}/files`).then((r) => r.data);
export const deleteKBFile = (fileId) => api.delete(`/kb/files/${fileId}`).then((r) => r.data);
export const buildKB = (projectId) => api.post("/kb/build", { project_id: projectId }).then((r) => r.data);
export const kbStatus = (projectId) => api.get(`/kb/${projectId}/status`).then((r) => r.data);
export const kbToon = (projectId) => api.get(`/kb/${projectId}/toon`).then((r) => r.data);
export const kbGlossary = (projectId) => api.get(`/kb/${projectId}/glossary`).then((r) => r.data);
export const owlExportUrl = (projectId) => `${API}/kb/${projectId}/owl-export`;
export const importModuleInventory = (projectId, file) => {
  const fd = new FormData();
  fd.append("project_id", projectId);
  fd.append("file", file);
  return api
    .post("/kb/import-module-inventory", fd, { headers: { "Content-Type": "multipart/form-data" } })
    .then((r) => r.data);
};
export const getModuleTraceability = (projectId) =>
  api.get(`/kb/${projectId}/module-traceability`).then((r) => r.data);

// Chat
export const listModels = () => api.get("/chat/models").then((r) => r.data);
export const chatHistory = (projectId, conversationId) =>
  api.get(`/chat/${projectId}/history`, { params: { conversation_id: conversationId } }).then((r) => r.data);
export const sendMessage = (payload) => api.post("/chat", payload).then((r) => r.data);

// SRS
export const getSRS = (projectId) => api.get(`/srs/${projectId}`).then((r) => r.data);
export const generateSRS = (projectId, conversationId, model) =>
  api.post("/srs/generate", { project_id: projectId, conversation_id: conversationId, model }).then((r) => r.data);
export const updateSRSSection = (projectId, section, content) =>
  api.put(`/srs/${projectId}/section`, { section, content }).then((r) => r.data);
export const freezeSRS = (projectId, user) =>
  api.post("/srs/freeze", { project_id: projectId, user }).then((r) => r.data);
export const unfreezeSRS = (projectId) => api.post("/srs/unfreeze", { project_id: projectId }).then((r) => r.data);
export const srsPdfUrl = (projectId) => `${API}/srs/${projectId}/export.pdf`;

// Prompts
export const listPrompts = () => api.get("/prompts").then((r) => r.data);
export const updatePrompt = (key, payload) => api.put(`/prompts/${key}`, payload).then((r) => r.data);
export const listProjectPrompts = (projectId) => api.get(`/prompts/project/${projectId}`).then((r) => r.data);
export const updateProjectPrompt = (projectId, key, payload) =>
  api.put(`/prompts/project/${projectId}/${key}`, payload).then((r) => r.data);

// Audit
export const listAudit = (projectId) =>
  api.get(`/audit`, { params: { project_id: projectId } }).then((r) => r.data);

// Data Model — Stage 2
export const generateOLTPUrl = () => `${API}/data-model/generate/oltp`;
export const generateOLAPUrl = () => `${API}/data-model/generate/olap`;
export const generateScriptsUrl = () => `${API}/data-model/generate/migration-scripts`;
// Job-based (recommended for OLAP + scripts — bypasses ~60s ingress timeout)
export const startOLAPJob = (projectId, model) =>
  api.post("/data-model/jobs/start/olap", { project_id: projectId, model }).then((r) => r.data);
export const startScriptsJob = (projectId, model) =>
  api.post("/data-model/jobs/start/scripts", { project_id: projectId, model }).then((r) => r.data);
export const getDataModelJob = (jobId) =>
  api.get(`/data-model/jobs/${jobId}`).then((r) => r.data);
export const generateBusMatrix = (projectId, model) =>
  api.post("/data-model/generate/bus-matrix", { project_id: projectId, model }).then((r) => r.data);
export const generateEntityGraph = (projectId) =>
  api.post("/data-model/generate/entity-graph", { project_id: projectId }).then((r) => r.data);
export const getDataModelArtifacts = (projectId) =>
  api.get(`/data-model/${projectId}/artifacts`).then((r) => r.data);
export const getArtifact = (projectId, artifactId) =>
  api.get(`/data-model/${projectId}/artifact/${artifactId}`).then((r) => r.data);
export const updateArtifact = (projectId, artifactId, content) =>
  api.put(`/data-model/${projectId}/artifact/${artifactId}`, { content }).then((r) => r.data);
export const freezeArtifact = (projectId, artifactId) =>
  api.post(`/data-model/${projectId}/artifact/${artifactId}/freeze`).then((r) => r.data);
export const downloadArtifactUrl = (projectId, artifactId) =>
  `${API}/data-model/${projectId}/artifact/${artifactId}/download`;
export const sendDataModelChat = (payload) =>
  api.post("/data-model/chat", payload).then((r) => r.data);
export const factoryReset = (projectId) =>
  api.post(`/projects/${projectId}/factory-reset`).then((r) => r.data);
export const resetStage2 = (projectId) =>
  api.post(`/data-model/${projectId}/reset`).then((r) => r.data);

// Architecture — Stage 3
export const startArchRecommend = (projectId, model, message) =>
  api.post("/architecture/jobs/start/recommend", { project_id: projectId, model, message }).then((r) => r.data);
export const startArchHld = (projectId, model) =>
  api.post("/architecture/jobs/start/hld", { project_id: projectId, model }).then((r) => r.data);
export const startArchLld = (projectId, model) =>
  api.post("/architecture/jobs/start/lld", { project_id: projectId, model }).then((r) => r.data);
export const startArchSequence = (projectId, model) =>
  api.post("/architecture/jobs/start/sequence", { project_id: projectId, model }).then((r) => r.data);
export const getArchJob = (jobId) =>
  api.get(`/architecture/jobs/${jobId}`).then((r) => r.data);
export const approveServiceMap = (projectId, approved = true, overrides = []) =>
  api.post("/architecture/approve", { project_id: projectId, approved, overrides }).then((r) => r.data);
export const sendArchChat = (payload) =>
  api.post("/architecture/chat", payload).then((r) => r.data);
export const applyArchChanges = (projectId, changes, conversationMessageId) =>
  api.post(`/architecture/${projectId}/apply-changes`, { changes, conversation_message_id: conversationMessageId }).then((r) => r.data);
export const getArchArtifacts = (projectId) =>
  api.get(`/architecture/${projectId}/artifacts`).then((r) => r.data);
export const getArchArtifact = (projectId, artifactId) =>
  api.get(`/architecture/${projectId}/artifact/${artifactId}`).then((r) => r.data);
export const updateArchArtifact = (projectId, artifactId, content) =>
  api.put(`/architecture/${projectId}/artifact/${artifactId}`, { content }).then((r) => r.data);
export const freezeArchArtifact = (projectId, artifactId) =>
  api.post(`/architecture/${projectId}/artifact/${artifactId}/freeze`).then((r) => r.data);
export const downloadArchArtifactUrl = (projectId, artifactId) =>
  `${API}/architecture/${projectId}/artifact/${artifactId}/download`;
export const resetArch = (projectId) =>
  api.post(`/architecture/${projectId}/reset`).then((r) => r.data);

// CodeGen — Stage 4
export const startCodegenJob = (projectId, model, serviceName) =>
  api.post("/codegen/jobs/start/generate", { project_id: projectId, model, service_name: serviceName || undefined }).then((r) => r.data);
export const getCodegenJob = (jobId) =>
  api.get(`/codegen/jobs/${jobId}`).then((r) => r.data);
export const listCodegenFiles = (projectId) =>
  api.get(`/codegen/${projectId}/files`).then((r) => r.data);
export const getCodegenFile = (projectId, fileId) =>
  api.get(`/codegen/${projectId}/file/${fileId}`).then((r) => r.data);
export const updateCodegenFile = (projectId, fileId, content) =>
  api.put(`/codegen/${projectId}/file/${fileId}`, { content }).then((r) => r.data);
export const downloadCodegenZipUrl = (projectId) =>
  `${API}/codegen/${projectId}/download-zip`;
export const startCodegenZipDownload = (projectId) =>
  api.post(`/codegen/${projectId}/download-zip`, null, { responseType: "blob" }).then((r) => r.data);
export const startGithubPushJob = (projectId) =>
  api.post("/codegen/jobs/start/github-push", { project_id: projectId }).then((r) => r.data);
export const sendCodegenChat = (payload) =>
  api.post("/codegen/chat", payload).then((r) => r.data);
export const applyCodegenFileChange = (projectId, fileId, newContent, conversationMessageId) =>
  api.post(`/codegen/${projectId}/apply-file-change`, { file_id: fileId, new_content: newContent, conversation_message_id: conversationMessageId }).then((r) => r.data);
export const freezeCodegen = (projectId) =>
  api.post(`/codegen/${projectId}/freeze`).then((r) => r.data);
export const resetCodegen = (projectId) =>
  api.post(`/codegen/${projectId}/reset`).then((r) => r.data);

export const getOntology = (projectId) =>
  api.get(`/kb/${projectId}/ontology`).then((r) => r.data);
export const createOntologySnapshot = (projectId, name) =>
  api.post(`/kb/${projectId}/ontology/snapshot`, { name }).then((r) => r.data);
export const listOntologySnapshots = (projectId) =>
  api.get(`/kb/${projectId}/ontology/snapshots`).then((r) => r.data);
export const deleteOntologySnapshot = (projectId, snapshotId) =>
  api.delete(`/kb/${projectId}/ontology/snapshot/${snapshotId}`).then((r) => r.data);
export const diffOntology = (projectId, a, b = "current") =>
  api.get(`/kb/${projectId}/ontology/diff`, { params: { a, b } }).then((r) => r.data);

// Living — Stage 5
export const startLivingJob = (kind, projectId, extra = {}) =>
  api.post(`/living/jobs/start/${kind}`, { project_id: projectId, ...extra }).then((r) => r.data);
export const getLivingJob = (jobId) =>
  api.get(`/living/jobs/${jobId}`).then((r) => r.data);
export const listLivingArtifacts = (projectId) =>
  api.get(`/living/${projectId}/artifacts`).then((r) => r.data);
export const getLivingArtifact = (projectId, artId) =>
  api.get(`/living/${projectId}/artifact/${artId}`).then((r) => r.data);
export const updateLivingArtifact = (projectId, artId, files) =>
  api.put(`/living/${projectId}/artifact/${artId}`, { files }).then((r) => r.data);
export const freezeLivingArtifact = (projectId, artId) =>
  api.post(`/living/${projectId}/artifact/${artId}/freeze`).then((r) => r.data);
export const downloadLivingArtifactUrl = (projectId, artId) =>
  `${API}/living/${projectId}/artifact/${artId}/download`;
export const freezeLiving = (projectId) =>
  api.post(`/living/${projectId}/freeze`).then((r) => r.data);
export const resetLiving = (projectId) =>
  api.post(`/living/${projectId}/reset`).then((r) => r.data);

// Console — Model Fabric
export const setupProvider = (data) =>
  api.post("/console/providers/setup", data).then((r) => r.data);
export const listProviders = () =>
  api.get("/console/providers").then((r) => r.data);
export const updateProvider = (id, data) =>
  api.put(`/console/providers/${id}`, data).then((r) => r.data);
export const updateProviderKey = (id, apiKey) =>
  api.put(`/console/providers/${id}/key`, { api_key: apiKey }).then((r) => r.data);
export const deleteProvider = (id) =>
  api.delete(`/console/providers/${id}`).then((r) => r.data);
export const testProvider = (id) =>
  api.post(`/console/providers/${id}/test`).then((r) => r.data);
export const fetchProviderModels = (id) =>
  api.post(`/console/providers/${id}/fetch-models`).then((r) => r.data);
export const listAvailableModels = () =>
  api.get("/console/models/available").then((r) => r.data);

// Console — Agent Fabric
export const listAgents = () =>
  api.get("/console/agents").then((r) => r.data);
export const getAgent = (key) =>
  api.get(`/console/agents/${encodeURIComponent(key)}`).then((r) => r.data);
export const updateAgent = (key, data) =>
  api.put(`/console/agents/${encodeURIComponent(key)}`, data).then((r) => r.data);
export const resetAgentBudget = (key) =>
  api.post(`/console/agents/${encodeURIComponent(key)}/reset-budget`).then((r) => r.data);
export const testAgent = (key, projectId) =>
  api.post(`/console/agents/${encodeURIComponent(key)}/test`, { project_id: projectId }).then((r) => r.data);
export const getAgentUsage = (key) =>
  api.get(`/console/agents/${encodeURIComponent(key)}/usage`).then((r) => r.data);

// Console — Usage
export const getUsageSummary = (projectId, days = 7) =>
  api.get(`/console/usage/summary`, { params: { project_id: projectId || "", days } }).then((r) => r.data);
export const getUsageLog = (params) =>
  api.get("/console/usage/log", { params }).then((r) => r.data);

// Console — Prompt engineering
export const previewPrompt = (promptKey, projectId) =>
  api.post("/console/prompts/preview", { prompt_key: promptKey, project_id: projectId }).then((r) => r.data);
export const testPrompt = (promptKey, projectId, modelOverride) =>
  api.post("/console/prompts/test", {
    prompt_key: promptKey, project_id: projectId, model_override: modelOverride || "",
  }).then((r) => r.data);

export default api;
