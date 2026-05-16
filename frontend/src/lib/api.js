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

export default api;
