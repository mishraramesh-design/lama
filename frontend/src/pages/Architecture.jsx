import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import mermaid from "mermaid";
import {
  Loader2,
  Sparkles,
  Download,
  Lock,
  Pencil,
  Check,
  Send,
  Boxes,
  GitBranch,
  FileText,
  RotateCcw,
  ChevronDown,
  ChevronRight as ChevronRightIcon,
  Workflow,
  Network,
  Wand2,
} from "lucide-react";
import { toast } from "sonner";
import { useProjects } from "@/state/ProjectContext";
import {
  startArchRecommend,
  startArchHld,
  startArchLld,
  startArchSequence,
  getArchJob,
  approveServiceMap,
  sendArchChat,
  applyArchChanges,
  getArchArtifacts,
  getArchArtifact,
  updateArchArtifact,
  freezeArchArtifact,
  downloadArchArtifactUrl,
  resetArch,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import MiniConsole from "@/components/MiniConsole";

mermaid.initialize({ startOnLoad: false, theme: "neutral", securityLevel: "loose", flowchart: { htmlLabels: true } });

const ARTIFACT_META = {
  service_map: { label: "Service Map", icon: Network, ext: "json" },
  hld: { label: "HLD — High-Level Design", icon: Boxes, ext: "md" },
  lld: { label: "LLD — Low-Level Design", icon: FileText, ext: "md" },
  sequence_diagrams: { label: "Sequence Diagrams", icon: Workflow, ext: "md" },
  api_contracts: { label: "API Contracts", icon: GitBranch, ext: "yaml" },
};

// -----------------------------------------------------------
// Mermaid block renderer (one diagram in a div)
// -----------------------------------------------------------
function MermaidBlock({ chart, id }) {
  const ref = useRef(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    if (!ref.current || !chart) return;
    let cancelled = false;
    const render = async () => {
      try {
        const cleaned = chart.trim();
        const { svg } = await mermaid.render(id, cleaned);
        if (!cancelled && ref.current) ref.current.innerHTML = svg;
      } catch (e) {
        if (!cancelled) setErr(String(e?.message || e));
      }
    };
    render();
    return () => { cancelled = true; };
  }, [chart, id]);
  if (err) {
    return (
      <pre className="text-[11px] bg-rose-50 border border-rose-200 text-rose-700 p-2 rounded-sm overflow-x-auto">{err}\n\n{chart}</pre>
    );
  }
  return <div ref={ref} data-testid={`mermaid-${id}`} className="bg-white border border-[#E6E6E6] rounded-sm p-3 overflow-x-auto" />;
}

// Render markdown with embedded mermaid fenced blocks
function MarkdownWithMermaid({ source, idPrefix }) {
  const parts = useMemo(() => {
    if (!source) return [];
    const out = [];
    const re = /```mermaid\n([\s\S]*?)```/g;
    let last = 0; let m; let i = 0;
    while ((m = re.exec(source)) !== null) {
      if (m.index > last) out.push({ type: "md", content: source.slice(last, m.index) });
      out.push({ type: "mermaid", content: m[1], key: `${idPrefix}-mm-${i++}` });
      last = m.index + m[0].length;
    }
    if (last < source.length) out.push({ type: "md", content: source.slice(last) });
    return out;
  }, [source, idPrefix]);
  if (!source) return <div className="text-xs text-[#747480]">No content yet.</div>;
  return (
    <div className="prose prose-sm max-w-none text-[#2E2E38]">
      {parts.map((p, i) =>
        p.type === "mermaid" ? (
          <MermaidBlock key={p.key} chart={p.content} id={p.key} />
        ) : (
          <ReactMarkdown key={i} remarkPlugins={[remarkGfm]}>
            {p.content}
          </ReactMarkdown>
        )
      )}
    </div>
  );
}

// -----------------------------------------------------------
// Reset modal (typed RESET)
// -----------------------------------------------------------
function ResetModal({ open, onClose, onConfirm, title, warning }) {
  const [typed, setTyped] = useState("");
  useEffect(() => { if (!open) setTyped(""); }, [open]);
  if (!open) return null;
  const enabled = typed === "RESET";
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" data-testid="arch-reset-modal">
      <div className="bg-white max-w-md w-full rounded-sm border-2 border-orange-500 p-5">
        <h3 className="font-display font-bold text-lg text-orange-700 flex items-center gap-2">
          <RotateCcw className="w-4 h-4" /> {title}
        </h3>
        <p className="text-xs text-[#2E2E38] mt-2 leading-snug">{warning}</p>
        <p className="text-xs text-[#747480] mt-3">Type <code className="bg-[#F6F6FA] px-1">RESET</code> to confirm.</p>
        <input
          autoFocus
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          data-testid="arch-reset-input"
          className="mt-1 w-full border border-[#E6E6E6] focus:border-orange-500 outline-none px-2 py-1.5 text-sm rounded-sm"
        />
        <div className="mt-4 flex justify-end gap-2">
          <button onClick={onClose} className="text-xs px-3 py-1.5 border border-[#E6E6E6] rounded-sm">Cancel</button>
          <button
            disabled={!enabled}
            onClick={onConfirm}
            data-testid="arch-reset-confirm"
            className={`text-xs px-3 py-1.5 rounded-sm font-bold text-white ${enabled ? "bg-orange-600 hover:bg-orange-700" : "bg-orange-300 cursor-not-allowed"}`}
          >
            Reset Stage 3
          </button>
        </div>
      </div>
    </div>
  );
}

// -----------------------------------------------------------
// Service Map JSON pretty viewer
// -----------------------------------------------------------
function ServiceMapView({ artifact }) {
  let data = {};
  try { data = JSON.parse(artifact?.content || "{}"); } catch { /* */ }
  const services = data.services || [];
  return (
    <div className="space-y-3" data-testid="service-map-view">
      <div className="flex items-center justify-between text-xs">
        <div>
          <span className="text-[#747480]">Recommended pattern:</span>{" "}
          <span className="font-bold text-[#2E2E38]" data-testid="recommended-pattern">{data.recommended_pattern || "—"}</span>
        </div>
        <div className="text-[#747480]">{services.length} service(s)</div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        {services.map((s, i) => (
          <div key={i} className="border border-[#E6E6E6] rounded-sm p-2 bg-white" data-testid={`service-card-${s.name}`}>
            <div className="flex items-center justify-between">
              <div className="font-semibold text-[13px]">{s.display_name || s.name}</div>
              <span className="text-[10px] uppercase bg-[#F6F6FA] px-1.5 py-0.5 rounded-sm">{s.backend_lang || "nodejs"}</span>
            </div>
            <div className="text-[11px] text-[#747480] mt-1">{s.responsibility}</div>
            {s.tables?.length > 0 && (
              <div className="text-[11px] mt-1"><span className="text-[#747480]">Tables:</span> {s.tables.slice(0, 6).join(", ")}{s.tables.length > 6 ? ` +${s.tables.length - 6}` : ""}</div>
            )}
            {s.api_endpoints?.length > 0 && (
              <div className="text-[11px] mt-0.5"><span className="text-[#747480]">Endpoints:</span> {s.api_endpoints.length}</div>
            )}
          </div>
        ))}
      </div>
      {data.event_bus && (
        <div className="text-[11px] text-[#2E2E38] bg-[#FFFCE6] border border-[#FFE600] rounded-sm p-2">
          Event bus enabled: {data.event_bus_type || "Kafka"}
        </div>
      )}
    </div>
  );
}

// -----------------------------------------------------------
// Job poll hook
// -----------------------------------------------------------
function useJobPoll(getter) {
  const [job, setJob] = useState(null);
  const [running, setRunning] = useState(false);
  const startId = useRef(null);
  useEffect(() => {
    if (!startId.current) return;
    let cancelled = false;
    const tick = async () => {
      try {
        const j = await getter(startId.current);
        if (cancelled) return;
        setJob(j);
        if (j.status === "complete" || j.status === "error") {
          setRunning(false);
          return;
        }
      } catch (e) { /* ignore */ }
      if (!cancelled) setTimeout(tick, 2000);
    };
    setRunning(true);
    tick();
    return () => { cancelled = true; };
  }, [job?.id, getter]); // eslint-disable-line
  const start = (jid) => { startId.current = jid; setJob({ id: jid, status: "queued", step: "Starting…", pct: 0 }); setRunning(true); };
  return { job, running, start };
}

// -----------------------------------------------------------
// Main page
// -----------------------------------------------------------
export default function ArchitecturePage() {
  const navigate = useNavigate();
  const { active } = useProjects();
  const projectId = active?.id;

  const [artifacts, setArtifacts] = useState([]);
  const [services, setServices] = useState([]);
  const [activeType, setActiveType] = useState("service_map");
  const [editing, setEditing] = useState(false);
  const [editBuf, setEditBuf] = useState("");
  const [chatMessages, setChatMessages] = useState([]);
  const [chatInput, setChatInput] = useState("");
  const [chatBusy, setChatBusy] = useState(false);
  const [convId, setConvId] = useState(null);
  const [target, setTarget] = useState("all");
  const [resetOpen, setResetOpen] = useState(false);
  const [model] = useState("deepseek/deepseek-chat");

  const status = active?.stage_status?.["Architecture"] || "locked";
  const dmStatus = active?.stage_status?.["DataModel"] || "locked";
  const isLocked = dmStatus !== "frozen";
  const isFrozen = status === "frozen";

  const recJob = useJobPoll(getArchJob);
  const hldJob = useJobPoll(getArchJob);
  const lldJob = useJobPoll(getArchJob);
  const seqJob = useJobPoll(getArchJob);

  const refresh = async () => {
    if (!projectId) return;
    try {
      const data = await getArchArtifacts(projectId);
      setArtifacts(data.artifacts || []);
      setServices(data.services || []);
    } catch (e) { /* ignore */ }
  };

  useEffect(() => { refresh(); }, [projectId]);

  // Re-fetch when any job completes
  useEffect(() => {
    if (recJob.job?.status === "complete" || hldJob.job?.status === "complete" || lldJob.job?.status === "complete" || seqJob.job?.status === "complete") {
      refresh();
    }
    if (recJob.job?.status === "error") toast.error("Recommend failed: " + recJob.job.error);
    if (hldJob.job?.status === "error") toast.error("HLD generation failed: " + hldJob.job.error);
    if (lldJob.job?.status === "error") toast.error("LLD generation failed: " + lldJob.job.error);
    if (seqJob.job?.status === "error") toast.error("Sequence diagrams failed: " + seqJob.job.error);
  }, [recJob.job?.status, hldJob.job?.status, lldJob.job?.status, seqJob.job?.status]); // eslint-disable-line

  const activeArtifact = useMemo(
    () => artifacts.find((a) => a.type === activeType) || null,
    [artifacts, activeType]
  );

  const startEdit = () => {
    if (!activeArtifact || activeArtifact.frozen) return;
    setEditBuf(activeArtifact.content || "");
    setEditing(true);
  };
  const saveEdit = async () => {
    if (!activeArtifact) return;
    try {
      await updateArchArtifact(projectId, activeArtifact.id, editBuf);
      toast.success("Saved");
      setEditing(false);
      await refresh();
    } catch (e) { toast.error("Save failed: " + (e?.response?.data?.detail || e.message)); }
  };

  const onFreeze = async (a) => {
    if (!a) return;
    try {
      await freezeArchArtifact(projectId, a.id);
      toast.success(`Froze ${ARTIFACT_META[a.type]?.label || a.type}`);
      await refresh();
    } catch (e) { toast.error("Freeze failed: " + (e?.response?.data?.detail || e.message)); }
  };

  const onApproveSm = async () => {
    try {
      await approveServiceMap(projectId, true, []);
      toast.success("Service map approved (frozen)");
      await refresh();
    } catch (e) { toast.error("Approve failed: " + (e?.response?.data?.detail || e.message)); }
  };

  const onRecommend = async () => {
    try {
      const r = await startArchRecommend(projectId, model, "");
      recJob.start(r.job_id);
      toast.message("Architecture recommendation started");
    } catch (e) { toast.error("Could not start: " + (e?.response?.data?.detail || e.message)); }
  };
  const onHld = async () => {
    const sm = artifacts.find((a) => a.type === "service_map");
    if (!sm || !sm.frozen) { toast.message("Approve the service map first."); return; }
    try { const r = await startArchHld(projectId, model); hldJob.start(r.job_id); }
    catch (e) { toast.error("Could not start HLD: " + (e?.response?.data?.detail || e.message)); }
  };
  const onLld = async () => {
    try { const r = await startArchLld(projectId, model); lldJob.start(r.job_id); }
    catch (e) { toast.error("Could not start LLD: " + (e?.response?.data?.detail || e.message)); }
  };
  const onSeq = async () => {
    try { const r = await startArchSequence(projectId, model); seqJob.start(r.job_id); }
    catch (e) { toast.error("Could not start sequence: " + (e?.response?.data?.detail || e.message)); }
  };

  const onSendChat = async () => {
    const m = chatInput.trim();
    if (!m) return;
    setChatBusy(true);
    setChatMessages((p) => [...p, { role: "user", content: m }]);
    setChatInput("");
    try {
      const r = await sendArchChat({ project_id: projectId, message: m, conversation_id: convId, target_artifact: target });
      setConvId(r.conversation_id);
      setChatMessages((p) => [...p, { role: "assistant", content: r.content, changes: r.changes || [], message_id: r.message_id }]);
    } catch (e) {
      toast.error("Chat failed: " + (e?.response?.data?.detail || e.message));
    } finally { setChatBusy(false); }
  };

  const onApplyChanges = async (changes, msgId) => {
    try {
      const r = await applyArchChanges(projectId, changes, msgId);
      toast.success(`Applied ${r.updated?.length || 0} change(s)`);
      await refresh();
    } catch (e) { toast.error("Apply failed: " + (e?.response?.data?.detail || e.message)); }
  };

  const onReset = async () => {
    try {
      await resetArch(projectId);
      toast.success("Stage 3 reset");
      setResetOpen(false);
      setArtifacts([]); setServices([]); setChatMessages([]); setConvId(null);
    } catch (e) { toast.error("Reset failed"); }
  };

  if (!projectId) return <div className="flex-1 p-8 text-sm text-[#747480]">No active project.</div>;

  // Locked view
  if (isLocked) {
    return (
      <div className="flex-1 flex flex-col bg-[#F6F6FA]" data-testid="arch-locked">
        <header className="bg-white border-b-2 border-[#FFE600] px-6 py-3">
          <div className="text-[10px] uppercase tracking-widest text-[#747480]">Stage 3 of 5</div>
          <h1 className="font-display text-lg font-bold tracking-tight text-[#2E2E38]">Architecture</h1>
        </header>
        <div className="flex-1 flex items-center justify-center p-8">
          <div className="max-w-md bg-white border border-[#E6E6E6] rounded-sm p-6 text-center">
            <Lock className="w-8 h-8 mx-auto text-[#747480] mb-3" />
            <h2 className="font-display font-bold text-[#2E2E38]">Locked — DataModel not frozen</h2>
            <p className="text-xs text-[#747480] mt-2">Freeze both OLTP and OLAP DDLs in Stage 2 to unlock Architecture.</p>
            <button onClick={() => navigate("/data-model")} className="mt-4 text-xs px-3 py-1.5 bg-[#2E2E38] text-white rounded-sm">Open DataModel →</button>
          </div>
        </div>
      </div>
    );
  }

  const tabs = [
    { type: "service_map", icon: Network, label: "Service Map" },
    { type: "hld", icon: Boxes, label: "HLD" },
    { type: "lld", icon: FileText, label: "LLD" },
    { type: "sequence_diagrams", icon: Workflow, label: "Sequence" },
    { type: "api_contracts", icon: GitBranch, label: "API Contracts" },
  ];

  return (
    <div className="flex-1 flex flex-col min-w-0 bg-[#F6F6FA]" data-testid="arch-page">
      <header className="bg-white border-b-2 border-[#FFE600] px-6 py-3 flex items-center justify-between">
        <div>
          <div className="text-[10px] uppercase tracking-widest text-[#747480]">Stage 3 of 5</div>
          <h1 className="font-display text-lg font-bold tracking-tight text-[#2E2E38]">Architecture</h1>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-[#747480]">{services.length} services · {artifacts.length} artifacts</span>
          {isFrozen && <span className="text-[10px] uppercase font-bold bg-[#FFE600] text-[#2E2E38] px-2 py-0.5 rounded-sm">Frozen</span>}
          <button onClick={() => setResetOpen(true)} data-testid="arch-reset-btn" className="text-xs px-2 py-1 border border-orange-300 text-orange-700 rounded-sm flex items-center gap-1 hover:bg-orange-50">
            <RotateCcw className="w-3 h-3" /> Reset
          </button>
        </div>
      </header>

      <div className="flex-1 min-h-0">
        <PanelGroup direction="horizontal">
          {/* LEFT: actions + chat */}
          <Panel defaultSize={30} minSize={22}>
            <div className="h-full bg-white border-r border-[#E6E6E6] flex flex-col">
              <div className="px-3 py-2 border-b border-[#E6E6E6]">
                <div className="mos-label mb-1">Generate</div>
                <div className="grid grid-cols-2 gap-1">
                  <Button data-testid="btn-recommend" onClick={onRecommend} disabled={recJob.running} className="h-8 text-[11px] bg-[#FFE600] text-[#2E2E38] hover:bg-[#FFD500]">
                    {recJob.running ? <Loader2 className="w-3 h-3 animate-spin" /> : <Wand2 className="w-3 h-3" />} Recommend
                  </Button>
                  <Button data-testid="btn-hld" onClick={onHld} disabled={hldJob.running} className="h-8 text-[11px]" variant="outline">
                    {hldJob.running ? <Loader2 className="w-3 h-3 animate-spin" /> : <Boxes className="w-3 h-3" />} HLD
                  </Button>
                  <Button data-testid="btn-lld" onClick={onLld} disabled={lldJob.running} className="h-8 text-[11px]" variant="outline">
                    {lldJob.running ? <Loader2 className="w-3 h-3 animate-spin" /> : <FileText className="w-3 h-3" />} LLD
                  </Button>
                  <Button data-testid="btn-seq" onClick={onSeq} disabled={seqJob.running} className="h-8 text-[11px]" variant="outline">
                    {seqJob.running ? <Loader2 className="w-3 h-3 animate-spin" /> : <Workflow className="w-3 h-3" />} Sequence
                  </Button>
                </div>
                <div className="mt-2 space-y-1">
                  {[{ j: recJob, k: "rec" }, { j: hldJob, k: "hld" }, { j: lldJob, k: "lld" }, { j: seqJob, k: "seq" }].filter(x => x.j.job).map(({ j, k }) => (
                    <div key={k} data-testid={`job-${k}`} className="text-[10px]">
                      <div className="flex items-center justify-between">
                        <span className="text-[#747480] truncate">{j.job.kind}: {j.job.step}</span>
                        <span className="text-[#2E2E38] font-semibold">{j.job.pct || 0}%</span>
                      </div>
                      <div className="h-1 bg-[#F6F6FA] rounded-sm overflow-hidden">
                        <div className="h-full bg-[#FFE600]" style={{ width: `${j.job.pct || 0}%` }} />
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="px-3 py-2 border-b border-[#E6E6E6] flex items-center gap-2">
                <div className="mos-label">Chat target</div>
                <select data-testid="chat-target" value={target} onChange={(e) => setTarget(e.target.value)} className="text-[11px] border border-[#E6E6E6] rounded-sm px-1 py-0.5">
                  <option value="all">All</option>
                  <option value="hld">HLD</option>
                  <option value="lld">LLD</option>
                  <option value="service_map">Service Map</option>
                  <option value="api_contracts">API Contracts</option>
                </select>
              </div>

              <div className="flex-1 overflow-y-auto mos-scroll p-3 space-y-2" data-testid="arch-chat-log">
                {chatMessages.length === 0 && (
                  <div className="text-[11px] text-[#747480]">Ask the architect-LLM to refine services, modify HLD sections, or update LLDs. The LLM may emit `[HLD_CHANGE:section]…[/HLD_CHANGE]`, `[ARCH_CHANGE:service]…[/ARCH_CHANGE]`, or `[SERVICE_ADD]…[/SERVICE_ADD]` — review and click Apply.</div>
                )}
                {chatMessages.map((m, i) => (
                  <div key={i} className={`text-[12px] p-2 rounded-sm ${m.role === "user" ? "bg-[#FFFCE6] border border-[#FFE600]" : "bg-[#F6F6FA] border border-[#E6E6E6]"}`}>
                    <div className="text-[9px] uppercase font-bold text-[#747480] mb-1">{m.role}</div>
                    <pre className="whitespace-pre-wrap text-[12px] leading-snug text-[#2E2E38]">{m.content}</pre>
                    {m.changes?.length > 0 && (
                      <div className="mt-1.5 flex flex-wrap gap-1">
                        <button onClick={() => onApplyChanges(m.changes, m.message_id)} data-testid={`apply-changes-${i}`} className="text-[10px] px-2 py-0.5 bg-[#2E2E38] text-white rounded-sm">
                          Apply {m.changes.length} change(s)
                        </button>
                        {m.changes.map((c, j) => (
                          <span key={j} className="text-[9px] uppercase bg-white border border-[#E6E6E6] px-1 py-0.5 rounded-sm">{c.type}{c.target ? `:${c.target}` : ""}</span>
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
                  placeholder="Refine architecture…"
                  data-testid="arch-chat-input"
                  className="flex-1 text-[12px] border border-[#E6E6E6] focus:border-[#2E2E38] outline-none rounded-sm px-2 py-1.5 resize-none"
                />
                <Button data-testid="arch-chat-send" onClick={onSendChat} disabled={chatBusy} className="h-auto bg-[#2E2E38] text-white px-3"><Send className="w-3 h-3" /></Button>
              </div>
            </div>
          </Panel>

          <PanelResizeHandle className="w-1 bg-[#E6E6E6] hover:bg-[#FFE600]" />

          {/* RIGHT: artifact viewer */}
          <Panel defaultSize={70}>
            <div className="h-full flex flex-col bg-white">
              {/* Tabs */}
              <div className="flex items-center border-b border-[#E6E6E6] px-2">
                {tabs.map((t) => {
                  const a = artifacts.find((x) => x.type === t.type);
                  const Icon = t.icon;
                  const isActive = activeType === t.type;
                  return (
                    <button
                      key={t.type}
                      data-testid={`tab-${t.type}`}
                      onClick={() => { setActiveType(t.type); setEditing(false); }}
                      className={`flex items-center gap-1 text-[12px] px-2.5 py-2 border-b-2 ${isActive ? "border-[#FFE600] text-[#2E2E38] font-semibold" : "border-transparent text-[#747480] hover:text-[#2E2E38]"}`}
                    >
                      <Icon className="w-3 h-3" /> {t.label}
                      {a?.frozen && <Lock className="w-3 h-3 text-[#FFE600]" />}
                      {a && !a.frozen && <span className="text-[9px] bg-[#F6F6FA] px-1 rounded-sm">v{a.version}</span>}
                    </button>
                  );
                })}
                <div className="ml-auto flex items-center gap-1 py-1">
                  {activeArtifact && !activeArtifact.frozen && !editing && (
                    <>
                      <button onClick={startEdit} data-testid="edit-artifact" className="text-[11px] px-2 py-1 border border-[#E6E6E6] hover:bg-[#F6F6FA] rounded-sm flex items-center gap-1"><Pencil className="w-3 h-3" /> Edit</button>
                      {activeType === "service_map" ? (
                        <button onClick={onApproveSm} data-testid="approve-service-map" className="text-[11px] px-2 py-1 bg-[#FFE600] text-[#2E2E38] rounded-sm font-bold flex items-center gap-1"><Check className="w-3 h-3" /> Approve</button>
                      ) : (
                        <button onClick={() => onFreeze(activeArtifact)} data-testid="freeze-artifact" className="text-[11px] px-2 py-1 bg-[#2E2E38] text-white rounded-sm flex items-center gap-1"><Lock className="w-3 h-3" /> Freeze</button>
                      )}
                    </>
                  )}
                  {activeArtifact && (
                    <a href={downloadArchArtifactUrl(projectId, activeArtifact.id)} data-testid="download-artifact" className="text-[11px] px-2 py-1 border border-[#E6E6E6] hover:bg-[#F6F6FA] rounded-sm flex items-center gap-1"><Download className="w-3 h-3" /></a>
                  )}
                </div>
              </div>

              {/* Body */}
              <div className="flex-1 overflow-y-auto mos-scroll p-4" data-testid={`artifact-body-${activeType}`}>
                {!activeArtifact && (
                  <div className="text-center text-[#747480] mt-12">
                    <Sparkles className="w-8 h-8 mx-auto mb-2 text-[#FFE600]" />
                    <div className="text-sm font-semibold">No {ARTIFACT_META[activeType]?.label || activeType} yet</div>
                    <div className="text-xs mt-1">Use Generate buttons on the left.</div>
                  </div>
                )}
                {editing && activeArtifact && (
                  <div className="flex flex-col gap-2 h-full">
                    <textarea
                      value={editBuf}
                      onChange={(e) => setEditBuf(e.target.value)}
                      data-testid="edit-textarea"
                      className="flex-1 min-h-[300px] text-[12px] font-mono border border-[#E6E6E6] focus:border-[#2E2E38] outline-none rounded-sm p-2"
                    />
                    <div className="flex justify-end gap-2">
                      <button onClick={() => setEditing(false)} className="text-[11px] px-3 py-1 border border-[#E6E6E6] rounded-sm">Cancel</button>
                      <button onClick={saveEdit} data-testid="save-edit" className="text-[11px] px-3 py-1 bg-[#2E2E38] text-white rounded-sm">Save</button>
                    </div>
                  </div>
                )}
                {!editing && activeArtifact && activeType === "service_map" && <ServiceMapView artifact={activeArtifact} />}
                {!editing && activeArtifact && activeType !== "service_map" && (
                  <MarkdownWithMermaid source={activeArtifact.content} idPrefix={activeType} />
                )}
              </div>
            </div>
          </Panel>
        </PanelGroup>
      </div>

      <ResetModal
        open={resetOpen}
        onClose={() => setResetOpen(false)}
        onConfirm={onReset}
        title="Reset Stage 3 — Architecture"
        warning="Removes all architecture artifacts (service map, HLD, LLD, sequence, contracts) and unlocks Architecture for re-generation. Stage 4 / Stage 5 contexts will also be cleared."
      />
      <MiniConsole stage="Architecture" projectId={projectId} />
    </div>
  );
}
