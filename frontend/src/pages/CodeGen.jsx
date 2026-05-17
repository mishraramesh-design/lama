import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import Editor from "@monaco-editor/react";
import {
  Loader2,
  Sparkles,
  Download,
  Lock,
  Pencil,
  Check,
  Send,
  Code2,
  FileText,
  RotateCcw,
  ChevronDown,
  ChevronRight as ChevronRightIcon,
  Github,
  PackageCheck,
  Wand2,
  FolderOpen,
  Folder,
  File as FileIcon,
} from "lucide-react";
import { toast } from "sonner";
import { useProjects } from "@/state/ProjectContext";
import {
  startCodegenJob,
  getCodegenJob,
  listCodegenFiles,
  getCodegenFile,
  updateCodegenFile,
  startCodegenZipDownload,
  startGithubPushJob,
  sendCodegenChat,
  applyCodegenFileChange,
  freezeCodegen,
  resetCodegen,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import MiniConsole from "@/components/MiniConsole";

// language detection by extension
const EXT_LANG = {
  js: "javascript", jsx: "javascript", ts: "typescript", tsx: "typescript",
  py: "python", java: "java", go: "go", rs: "rust", rb: "ruby",
  json: "json", yml: "yaml", yaml: "yaml", md: "markdown", txt: "plaintext",
  sql: "sql", xml: "xml", html: "html", css: "css", sh: "shell",
  Dockerfile: "dockerfile", dockerfile: "dockerfile", env: "ini",
};
function pathLang(path = "") {
  const base = path.split("/").pop() || path;
  if (base.toLowerCase() === "dockerfile") return "dockerfile";
  const ext = base.split(".").pop();
  return EXT_LANG[ext] || "plaintext";
}

// -----------------------------------------------------------
// Reset modal
// -----------------------------------------------------------
function ResetModal({ open, onClose, onConfirm, title, warning }) {
  const [typed, setTyped] = useState("");
  useEffect(() => { if (!open) setTyped(""); }, [open]);
  if (!open) return null;
  const enabled = typed === "RESET";
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" data-testid="codegen-reset-modal">
      <div className="bg-white max-w-md w-full rounded-sm border-2 border-orange-500 p-5">
        <h3 className="font-display font-bold text-lg text-orange-700 flex items-center gap-2"><RotateCcw className="w-4 h-4" /> {title}</h3>
        <p className="text-xs text-[#2E2E38] mt-2 leading-snug">{warning}</p>
        <p className="text-xs text-[#747480] mt-3">Type <code className="bg-[#F6F6FA] px-1">RESET</code> to confirm.</p>
        <input autoFocus value={typed} onChange={(e) => setTyped(e.target.value)} data-testid="codegen-reset-input" className="mt-1 w-full border border-[#E6E6E6] focus:border-orange-500 outline-none px-2 py-1.5 text-sm rounded-sm" />
        <div className="mt-4 flex justify-end gap-2">
          <button onClick={onClose} className="text-xs px-3 py-1.5 border border-[#E6E6E6] rounded-sm">Cancel</button>
          <button disabled={!enabled} onClick={onConfirm} data-testid="codegen-reset-confirm" className={`text-xs px-3 py-1.5 rounded-sm font-bold text-white ${enabled ? "bg-orange-600 hover:bg-orange-700" : "bg-orange-300 cursor-not-allowed"}`}>Reset Stage 4</button>
        </div>
      </div>
    </div>
  );
}

// -----------------------------------------------------------
// File tree nesting helper (group flat paths into nested folders)
// -----------------------------------------------------------
function buildTree(files) {
  // files: [{ path, ... }]
  const root = { name: "", dirs: {}, files: [] };
  for (const f of files) {
    const parts = f.path.split("/");
    let cur = root;
    for (let i = 0; i < parts.length - 1; i++) {
      const p = parts[i];
      if (!cur.dirs[p]) cur.dirs[p] = { name: p, dirs: {}, files: [] };
      cur = cur.dirs[p];
    }
    cur.files.push({ ...f, basename: parts[parts.length - 1] });
  }
  return root;
}

// Flatten tree to a list of rows (no recursive JSX)
function flattenTree(root, expanded) {
  const rows = [];
  const walk = (node, depth, baseKey) => {
    const dirs = Object.values(node.dirs).sort((a, b) => a.name.localeCompare(b.name));
    for (const d of dirs) {
      const key = baseKey ? `${baseKey}/${d.name}` : d.name;
      const isOpen = expanded[key] !== false; // default open
      rows.push({ kind: "dir", key, name: d.name, depth, isOpen });
      if (isOpen) walk(d, depth + 1, key);
    }
    for (const f of node.files) {
      rows.push({ kind: "file", key: f.id, depth: depth + 1, file: f });
    }
  };
  walk(root, 0, "");
  return rows;
}

// -----------------------------------------------------------
// useJobPoll
// -----------------------------------------------------------
function useJobPoll(getter, onComplete) {
  const [job, setJob] = useState(null);
  const [running, setRunning] = useState(false);
  const startId = useRef(null);
  useEffect(() => {
    if (!startId.current || !job) return;
    let cancelled = false;
    const tick = async () => {
      try {
        const j = await getter(startId.current);
        if (cancelled) return;
        setJob(j);
        if (j.status === "complete" || j.status === "error") {
          setRunning(false);
          if (j.status === "complete" && onComplete) onComplete(j);
          return;
        }
      } catch (e) { /* ignore */ }
      if (!cancelled) setTimeout(tick, 2000);
    };
    setRunning(true);
    tick();
    return () => { cancelled = true; };
  }, [job?.id]); // eslint-disable-line
  const start = (jid) => { startId.current = jid; setJob({ id: jid, status: "queued", step: "Starting…", pct: 0 }); setRunning(true); };
  return { job, running, start };
}

// -----------------------------------------------------------
// Main
// -----------------------------------------------------------
export default function CodeGenPage() {
  const navigate = useNavigate();
  const { active } = useProjects();
  const projectId = active?.id;
  const archStatus = active?.stage_status?.["Architecture"] || "locked";
  const status = active?.stage_status?.["CodeGen"] || "locked";
  const isLocked = archStatus !== "frozen";
  const isFrozen = status === "frozen";

  const [tree, setTree] = useState([]);     // [{ name, files: [...] }]
  const [totalFiles, setTotalFiles] = useState(0);
  const [expanded, setExpanded] = useState({});
  const [selectedFile, setSelectedFile] = useState(null);
  const [fileContent, setFileContent] = useState("");
  const [editBuf, setEditBuf] = useState("");
  const [editing, setEditing] = useState(false);
  const [chatMessages, setChatMessages] = useState([]);
  const [chatInput, setChatInput] = useState("");
  const [chatBusy, setChatBusy] = useState(false);
  const [convId, setConvId] = useState(null);
  const [resetOpen, setResetOpen] = useState(false);
  const [zipBusy, setZipBusy] = useState(false);
  const [model] = useState("deepseek/deepseek-chat");
  const [filterService, setFilterService] = useState("");

  const genJob = useJobPoll(getCodegenJob, () => refresh());
  const pushJob = useJobPoll(getCodegenJob);

  const refresh = async () => {
    if (!projectId) return;
    try {
      const data = await listCodegenFiles(projectId);
      setTree(data.services || []);
      setTotalFiles(data.total_files || 0);
    } catch (e) { /* ignore */ }
  };
  useEffect(() => { refresh(); }, [projectId]);

  useEffect(() => {
    if (genJob.job?.status === "error") toast.error("Codegen failed: " + genJob.job.error);
    if (pushJob.job?.status === "error") toast.error("GitHub push failed: " + pushJob.job.error);
    if (pushJob.job?.status === "complete") toast.success("Pushed to GitHub: " + (pushJob.job.result?.commit_sha?.slice(0, 8) || "ok"));
  }, [genJob.job?.status, pushJob.job?.status]);

  const flatFiles = useMemo(() => {
    const out = [];
    for (const s of tree) {
      if (filterService && s.name !== filterService) continue;
      for (const f of s.files) out.push({ ...f, service_name: s.name });
    }
    return out;
  }, [tree, filterService]);

  const builtTree = useMemo(() => buildTree(flatFiles), [flatFiles]);
  const treeRows = useMemo(() => flattenTree(builtTree, expanded), [builtTree, expanded]);
  const services = useMemo(() => tree.map((s) => s.name), [tree]);

  const onSelectFile = async (f) => {
    setSelectedFile(f);
    setEditing(false);
    setFileContent("Loading…");
    try {
      const doc = await getCodegenFile(projectId, f.id);
      setFileContent(doc.content || "");
    } catch (e) { toast.error("Could not load file"); }
  };

  const onGenerate = async () => {
    try {
      const r = await startCodegenJob(projectId, model, null);
      genJob.start(r.job_id);
      toast.message("Code generation started");
    } catch (e) { toast.error("Could not start: " + (e?.response?.data?.detail || e.message)); }
  };

  const onGenerateOne = async () => {
    if (!filterService) { toast.message("Select a service in the filter first"); return; }
    try {
      const r = await startCodegenJob(projectId, model, filterService);
      genJob.start(r.job_id);
    } catch (e) { toast.error("Could not start: " + (e?.response?.data?.detail || e.message)); }
  };

  const onDownloadZip = async () => {
    setZipBusy(true);
    try {
      const blob = await startCodegenZipDownload(projectId);
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = (active?.name || "lama").toLowerCase().replace(/\s+/g, "_") + ".zip";
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) { toast.error("Download failed: " + (e?.response?.data?.detail || e.message)); }
    finally { setZipBusy(false); }
  };

  const onPush = async () => {
    try {
      const r = await startGithubPushJob(projectId);
      pushJob.start(r.job_id);
    } catch (e) { toast.error("Could not start push: " + (e?.response?.data?.detail || e.message)); }
  };

  const onFreeze = async () => {
    try {
      await freezeCodegen(projectId);
      toast.success("Stage 4 frozen — Living unlocked");
    } catch (e) { toast.error("Freeze failed: " + (e?.response?.data?.detail || e.message)); }
  };

  const onSaveFile = async () => {
    if (!selectedFile) return;
    try {
      await updateCodegenFile(projectId, selectedFile.id, editBuf);
      setFileContent(editBuf);
      setEditing(false);
      toast.success("File saved");
      await refresh();
    } catch (e) { toast.error("Save failed"); }
  };

  const onSendChat = async () => {
    const m = chatInput.trim();
    if (!m) return;
    setChatBusy(true);
    setChatMessages((p) => [...p, { role: "user", content: m }]);
    setChatInput("");
    try {
      const r = await sendCodegenChat({
        project_id: projectId, message: m, conversation_id: convId,
        file_id: selectedFile?.id, service_name: filterService || selectedFile?.service_name,
      });
      setConvId(r.conversation_id);
      setChatMessages((p) => [...p, { role: "assistant", content: r.content, file_changes: r.file_changes || [], message_id: r.message_id }]);
    } catch (e) { toast.error("Chat failed: " + (e?.response?.data?.detail || e.message)); }
    finally { setChatBusy(false); }
  };

  const onApplyFileChange = async (fc, msgId) => {
    if (!fc.file_id) { toast.message("Target file not in repo. Generate it first."); return; }
    try {
      await applyCodegenFileChange(projectId, fc.file_id, fc.new_content, msgId);
      toast.success("Applied to " + fc.file_path);
      if (selectedFile?.id === fc.file_id) {
        setFileContent(fc.new_content);
      }
      await refresh();
    } catch (e) { toast.error("Apply failed"); }
  };

  const onReset = async () => {
    try {
      await resetCodegen(projectId);
      toast.success("Stage 4 reset");
      setResetOpen(false);
      setTree([]); setTotalFiles(0); setSelectedFile(null); setFileContent("");
      setChatMessages([]); setConvId(null);
    } catch (e) { toast.error("Reset failed"); }
  };

  const toggle = (k) => setExpanded((p) => ({ ...p, [k]: p[k] === false ? true : false }));

  if (!projectId) return <div className="flex-1 p-8 text-sm text-[#747480]">No active project.</div>;

  if (isLocked) {
    return (
      <div className="flex-1 flex flex-col bg-[#F6F6FA]" data-testid="codegen-locked">
        <header className="bg-white border-b-2 border-[#FFE600] px-6 py-3">
          <div className="text-[10px] uppercase tracking-widest text-[#747480]">Stage 4 of 5</div>
          <h1 className="font-display text-lg font-bold tracking-tight text-[#2E2E38]">Code Generation</h1>
        </header>
        <div className="flex-1 flex items-center justify-center p-8">
          <div className="max-w-md bg-white border border-[#E6E6E6] rounded-sm p-6 text-center">
            <Lock className="w-8 h-8 mx-auto text-[#747480] mb-3" />
            <h2 className="font-display font-bold text-[#2E2E38]">Locked — Architecture not frozen</h2>
            <p className="text-xs text-[#747480] mt-2">Freeze the service map, HLD, and LLD in Stage 3 to unlock CodeGen.</p>
            <button onClick={() => navigate("/architecture")} className="mt-4 text-xs px-3 py-1.5 bg-[#2E2E38] text-white rounded-sm">Open Architecture →</button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col min-w-0 bg-[#F6F6FA]" data-testid="codegen-page">
      <header className="bg-white border-b-2 border-[#FFE600] px-6 py-3 flex items-center justify-between">
        <div>
          <div className="text-[10px] uppercase tracking-widest text-[#747480]">Stage 4 of 5</div>
          <h1 className="font-display text-lg font-bold tracking-tight text-[#2E2E38]">Code Generation</h1>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-[#747480]">{totalFiles} files · {services.length} services</span>
          {isFrozen && <span className="text-[10px] uppercase font-bold bg-[#FFE600] text-[#2E2E38] px-2 py-0.5 rounded-sm">Frozen</span>}
          <Button data-testid="btn-generate" onClick={onGenerate} disabled={genJob.running} className="h-7 text-[11px] bg-[#FFE600] text-[#2E2E38] hover:bg-[#FFD500]">
            {genJob.running ? <Loader2 className="w-3 h-3 animate-spin" /> : <Wand2 className="w-3 h-3" />} Generate All
          </Button>
          <Button data-testid="btn-zip" onClick={onDownloadZip} disabled={zipBusy || totalFiles === 0} className="h-7 text-[11px]" variant="outline">
            {zipBusy ? <Loader2 className="w-3 h-3 animate-spin" /> : <Download className="w-3 h-3" />} ZIP
          </Button>
          <Button data-testid="btn-push" onClick={onPush} disabled={pushJob.running || totalFiles === 0} className="h-7 text-[11px]" variant="outline">
            {pushJob.running ? <Loader2 className="w-3 h-3 animate-spin" /> : <Github className="w-3 h-3" />} Push
          </Button>
          {!isFrozen && (
            <Button data-testid="btn-freeze-codegen" onClick={onFreeze} disabled={totalFiles === 0} className="h-7 text-[11px] bg-[#2E2E38] text-white">
              <PackageCheck className="w-3 h-3" /> Freeze
            </Button>
          )}
          <button onClick={() => setResetOpen(true)} data-testid="btn-reset-codegen" className="text-xs px-2 py-1 border border-orange-300 text-orange-700 rounded-sm flex items-center gap-1 hover:bg-orange-50">
            <RotateCcw className="w-3 h-3" /> Reset
          </button>
        </div>
      </header>

      {/* Job progress strip */}
      {(genJob.job || pushJob.job) && (
        <div className="bg-white border-b border-[#E6E6E6] px-4 py-1.5 space-y-1">
          {genJob.job && (
            <div className="text-[10px]" data-testid="codegen-job-bar">
              <div className="flex items-center justify-between">
                <span className="text-[#747480] truncate">codegen: {genJob.job.step}</span>
                <span className="text-[#2E2E38] font-semibold">{genJob.job.pct || 0}%</span>
              </div>
              <div className="h-1 bg-[#F6F6FA] rounded-sm overflow-hidden"><div className="h-full bg-[#FFE600]" style={{ width: `${genJob.job.pct || 0}%` }} /></div>
            </div>
          )}
          {pushJob.job && (
            <div className="text-[10px]" data-testid="push-job-bar">
              <div className="flex items-center justify-between">
                <span className="text-[#747480] truncate">github push: {pushJob.job.step}</span>
                <span className="text-[#2E2E38] font-semibold">{pushJob.job.pct || 0}%</span>
              </div>
              <div className="h-1 bg-[#F6F6FA] rounded-sm overflow-hidden"><div className="h-full bg-[#2E2E38]" style={{ width: `${pushJob.job.pct || 0}%` }} /></div>
            </div>
          )}
        </div>
      )}

      <div className="flex-1 min-h-0">
        <PanelGroup direction="horizontal">
          {/* LEFT: file tree */}
          <Panel defaultSize={20} minSize={14}>
            <div className="h-full bg-white border-r border-[#E6E6E6] flex flex-col">
              <div className="px-2 py-1.5 border-b border-[#E6E6E6] flex items-center gap-1">
                <select data-testid="service-filter" value={filterService} onChange={(e) => setFilterService(e.target.value)} className="text-[11px] border border-[#E6E6E6] rounded-sm px-1 py-0.5 flex-1">
                  <option value="">All services</option>
                  {services.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
                {filterService && (
                  <button onClick={onGenerateOne} title="Regenerate this service" data-testid="btn-regen-service" className="text-[10px] px-1.5 py-0.5 bg-[#FFE600] text-[#2E2E38] rounded-sm font-bold">↻</button>
                )}
              </div>
              <div className="flex-1 overflow-y-auto mos-scroll py-1" data-testid="file-tree">
                {flatFiles.length === 0 && (
                  <div className="text-[11px] text-[#747480] p-3">No files yet. Click <strong>Generate All</strong>.</div>
                )}
                {treeRows.map((r) => {
                  if (r.kind === "dir") {
                    return (
                      <button key={`d:${r.key}`} onClick={() => toggle(r.key)} data-testid={`dir-${r.key}`} className="w-full flex items-center gap-1 text-[11px] py-0.5 hover:bg-[#F6F6FA]" style={{ paddingLeft: 8 + r.depth * 10 }}>
                        {r.isOpen ? <ChevronDown className="w-3 h-3 text-[#747480]" /> : <ChevronRightIcon className="w-3 h-3 text-[#747480]" />}
                        {r.isOpen ? <FolderOpen className="w-3 h-3 text-[#FFE600]" /> : <Folder className="w-3 h-3 text-[#FFE600]" />}
                        <span className="text-[#2E2E38] truncate">{r.name}</span>
                      </button>
                    );
                  }
                  const f = r.file;
                  const isSel = selectedFile?.id === f.id;
                  return (
                    <button
                      key={`f:${f.id}`}
                      onClick={() => onSelectFile(f)}
                      data-testid={`file-${f.path}`}
                      className={`w-full flex items-center gap-1 text-[11px] py-0.5 ${isSel ? "bg-[#FFFCE6] text-[#2E2E38] font-semibold" : "hover:bg-[#F6F6FA] text-[#2E2E38]"}`}
                      style={{ paddingLeft: 8 + r.depth * 10 }}
                    >
                      <FileIcon className="w-3 h-3 text-[#747480]" />
                      <span className="truncate">{f.basename}</span>
                      {f.edited && <span className="text-[9px] text-orange-500 ml-auto">●</span>}
                    </button>
                  );
                })}
              </div>
            </div>
          </Panel>

          <PanelResizeHandle className="w-1 bg-[#E6E6E6] hover:bg-[#FFE600]" />

          {/* CENTER: editor */}
          <Panel defaultSize={50}>
            <div className="h-full flex flex-col bg-white">
              <div className="px-3 py-1.5 border-b border-[#E6E6E6] flex items-center gap-2">
                {selectedFile ? (
                  <>
                    <FileText className="w-3 h-3 text-[#747480]" />
                    <span className="text-[12px] font-mono text-[#2E2E38] truncate flex-1" data-testid="selected-file-path">{selectedFile.path}</span>
                    <span className="text-[9px] uppercase bg-[#F6F6FA] px-1 rounded-sm">v{selectedFile.version}</span>
                    {!editing && (
                      <button onClick={() => { setEditBuf(fileContent); setEditing(true); }} data-testid="edit-file-btn" className="text-[11px] px-2 py-1 border border-[#E6E6E6] hover:bg-[#F6F6FA] rounded-sm flex items-center gap-1"><Pencil className="w-3 h-3" /> Edit</button>
                    )}
                    {editing && (
                      <>
                        <button onClick={() => setEditing(false)} className="text-[11px] px-2 py-1 border border-[#E6E6E6] rounded-sm">Cancel</button>
                        <button onClick={onSaveFile} data-testid="save-file-btn" className="text-[11px] px-2 py-1 bg-[#2E2E38] text-white rounded-sm flex items-center gap-1"><Check className="w-3 h-3" /> Save</button>
                      </>
                    )}
                  </>
                ) : (
                  <span className="text-[11px] text-[#747480]">No file selected</span>
                )}
              </div>
              <div className="flex-1 min-h-0">
                {!selectedFile && (
                  <div className="h-full flex items-center justify-center text-[#747480]">
                    <div className="text-center">
                      <Sparkles className="w-8 h-8 mx-auto mb-2 text-[#FFE600]" />
                      <div className="text-sm">Select a file from the tree to view or edit it.</div>
                    </div>
                  </div>
                )}
                {selectedFile && (
                  <Editor
                    height="100%"
                    path={selectedFile.path}
                    language={pathLang(selectedFile.path)}
                    value={editing ? editBuf : fileContent}
                    onChange={(v) => editing && setEditBuf(v ?? "")}
                    options={{
                      readOnly: !editing,
                      minimap: { enabled: false },
                      fontSize: 12,
                      lineNumbers: "on",
                      scrollBeyondLastLine: false,
                      automaticLayout: true,
                    }}
                  />
                )}
              </div>
            </div>
          </Panel>

          <PanelResizeHandle className="w-1 bg-[#E6E6E6] hover:bg-[#FFE600]" />

          {/* RIGHT: chat */}
          <Panel defaultSize={30} minSize={20}>
            <div className="h-full bg-white flex flex-col">
              <div className="px-3 py-2 border-b border-[#E6E6E6] flex items-center gap-1">
                <Code2 className="w-3 h-3" />
                <span className="text-[11px] font-semibold">Code Chat</span>
                <span className="text-[10px] text-[#747480] ml-auto truncate">
                  {selectedFile ? `→ ${selectedFile.basename || selectedFile.path.split("/").pop()}` : "no file"}
                </span>
              </div>
              <div className="flex-1 overflow-y-auto mos-scroll p-3 space-y-2" data-testid="codegen-chat-log">
                {chatMessages.length === 0 && (
                  <div className="text-[11px] text-[#747480]">Ask the codegen-LLM to refactor, fix, or add tests. The LLM may emit one or more <code>[FILE_CHANGE:path/to/file]…[/FILE_CHANGE]</code> blocks — review and click Apply.</div>
                )}
                {chatMessages.map((m, i) => (
                  <div key={i} className={`text-[12px] p-2 rounded-sm ${m.role === "user" ? "bg-[#FFFCE6] border border-[#FFE600]" : "bg-[#F6F6FA] border border-[#E6E6E6]"}`}>
                    <div className="text-[9px] uppercase font-bold text-[#747480] mb-1">{m.role}</div>
                    <pre className="whitespace-pre-wrap text-[12px] leading-snug text-[#2E2E38]">{m.content}</pre>
                    {m.file_changes?.length > 0 && (
                      <div className="mt-1.5 space-y-1">
                        {m.file_changes.map((fc, j) => (
                          <div key={j} className="text-[10px] flex items-center gap-1">
                            <span className="font-mono truncate flex-1">{fc.file_path}</span>
                            <button onClick={() => onApplyFileChange(fc, m.message_id)} data-testid={`apply-fc-${i}-${j}`} className="px-2 py-0.5 bg-[#2E2E38] text-white rounded-sm">Apply</button>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
                {chatBusy && <div className="text-[11px] text-[#747480] flex items-center gap-1"><Loader2 className="w-3 h-3 animate-spin" /> Thinking…</div>}
              </div>
              <div className="border-t border-[#E6E6E6] p-2 flex gap-1">
                <textarea
                  rows={2}
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); onSendChat(); } }}
                  placeholder="Ask about the code…"
                  data-testid="codegen-chat-input"
                  className="flex-1 text-[12px] border border-[#E6E6E6] focus:border-[#2E2E38] outline-none rounded-sm px-2 py-1.5 resize-none"
                />
                <Button data-testid="codegen-chat-send" onClick={onSendChat} disabled={chatBusy} className="h-auto bg-[#2E2E38] text-white px-3"><Send className="w-3 h-3" /></Button>
              </div>
            </div>
          </Panel>
        </PanelGroup>
      </div>

      <ResetModal
        open={resetOpen}
        onClose={() => setResetOpen(false)}
        onConfirm={onReset}
        title="Reset Stage 4 — CodeGen"
        warning="Removes all generated files and codegen runs. Stage 5 (Living) context will also be cleared."
      />
      <MiniConsole stage="CodeGen" projectId={projectId} />
    </div>
  );
}
