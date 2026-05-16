import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

const api = axios.create({ baseURL: API, timeout: 600000 });

// Projects
export const listProjects = () => api.get("/projects").then((r) => r.data);
export const getProject = (id) => api.get(`/projects/${id}`).then((r) => r.data);

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

export default api;
