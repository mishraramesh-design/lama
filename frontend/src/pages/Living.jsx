import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Loader2, Lock, Activity, FlaskConical, GaugeCircle, FileSearch,
  GitCompare, Download, RotateCcw, Wand2, ChevronDown, ChevronRight as ChevronRightIcon,
  CheckCircle2, AlertTriangle,
} from "lucide-react";
import { toast } from "sonner";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useProjects } from "@/state/ProjectContext";
import {
  startLivingJob, getLivingJob,
  listLivingArtifacts, getLivingArtifact, updateLivingArtifact,
  freezeLivingArtifact, downloadLivingArtifactUrl,
  freezeLiving, resetLiving,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import MiniConsole from "@/components/MiniConsole";

const TABS = [
  { id: "selenium", label: "Selenium Tests", icon: FlaskConical },
  { id: "jmeter",   label: "JMeter Plans",  icon: GaugeCircle },
  { id: "drift",    label: "Drift Detector", icon: FileSearch },
  { id: "srs_diff", label: "SRS Diff",      icon: GitCompare },
];

// poll a job until completion
function useJob(getter, onComplete) {
  const [job, setJob] = useState(null);
  const start = useCallback((jid) => {
    setJob({ id: jid, status: "queued", step: "queued", pct: 0 });
    let stopped = false;
    const tick = async () => {
      if (stopped) return;
      try {
        const j = await getter(jid);
        setJob(j);
        if (j.status === "complete" || j.status === "error") { onComplete && onComplete(j); return; }
      } catch { /* */ }
      setTimeout(tick, 2000);
    };
    tick();
    return () => { stopped = true; };
  }, [getter, onComplete]);
  return { job, start, reset: () => setJob(null) };
}

function ResetModal({ open, onClose, onConfirm }) {
  const [t, setT] = useState("");
  useEffect(() => { if (!open) setT(""); }, [open]);
  if (!open) return null;
  const enabled = t === "RESET";
  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center" data-testid="living-reset-modal">
      <div className="bg-white border-2 border-orange-500 max-w-md w-full rounded-sm p-5">
        <h3 className="font-display font-bold text-orange-700 flex items-center gap-1"><RotateCcw className="w-4 h-4" /> Reset Stage 5 — Living</h3>
        <p className="text-xs text-[#2E2E38] mt-2">Deletes all Selenium / JMeter / Drift / SRS-diff artifacts and unlocks Living for re-generation.</p>
        <p className="text-[10px] text-[#747480] mt-2">Type <code className="bg-[#F6F6FA] px-1">RESET</code> to confirm.</p>
        <input value={t} onChange={(e) => setT(e.target.value)} data-testid="living-reset-input" className="w-full text-sm border border-[#E6E6E6] focus:border-orange-500 outline-none rounded-sm px-2 py-1.5 mt-1" autoFocus />
        <div className="flex justify-end gap-2 mt-3">
          <button onClick={onClose} className="text-xs px-3 py-1.5 border border-[#E6E6E6] rounded-sm">Cancel</button>
          <button disabled={!enabled} onClick={onConfirm} data-testid="living-reset-confirm" className={`text-xs px-3 py-1.5 rounded-sm font-bold text-white ${enabled ? "bg-orange-600 hover:bg-orange-700" : "bg-orange-300 cursor-not-allowed"}`}>Reset Stage 5</button>
        </div>
      </div>
    </div>
  );
}

function ProgressBar({ job, label }) {
  if (!job) return null;
  if (job.status === "error") {
    return (
      <div className="text-[11px] bg-rose-50 border border-rose-200 text-rose-700 p-2 rounded-sm" data-testid={`job-error-${label}`}>
        <AlertTriangle className="w-3 h-3 inline mr-1" /> {job.error || "Failed"}
      </div>
    );
  }
  return (
    <div className="space-y-1" data-testid={`job-progress-${label}`}>
      <div className="flex items-center justify-between text-[10px]">
        <span className="text-[#747480] truncate">{label}: {job.step}</span>
        <span className="text-[#2E2E38] font-semibold">{job.pct || 0}%</span>
      </div>
      <div className="h-1 bg-[#F6F6FA] rounded-sm overflow-hidden">
        <div className="h-full bg-[#FFE600] transition-all" style={{ width: `${job.pct || 0}%` }} />
      </div>
    </div>
  );
}

function ArtifactPanel({ kind, artifact, projectId, onRefresh }) {
  const [editing, setEditing] = useState(false);
  const [editFiles, setEditFiles] = useState([]);
  const [openIdx, setOpenIdx] = useState(0);

  useEffect(() => { if (artifact) setEditFiles(artifact.files || []); }, [artifact?.id, artifact?.version]); // eslint-disable-line

  if (!artifact) {
    return (
      <div className="p-6 text-center text-[#747480] text-[11px]">
        Nothing generated yet for <strong>{kind}</strong>. Click <strong>Generate</strong> above.
      </div>
    );
  }

  const onSave = async () => {
    try { await updateLivingArtifact(projectId, artifact.id, editFiles); toast.success("Saved"); setEditing(false); onRefresh(); }
    catch (e) { toast.error("Save failed: " + (e?.response?.data?.detail || e.message)); }
  };
  const onFreeze = async () => {
    try { await freezeLivingArtifact(projectId, artifact.id); toast.success("Frozen"); onRefresh(); }
    catch (e) { toast.error("Freeze failed"); }
  };

  const files = editing ? editFiles : (artifact.files || []);
  const isMarkdownKind = kind === "drift" || kind === "srs_diff";

  return (
    <div className="bg-white border border-[#E6E6E6] rounded-sm" data-testid={`artifact-${kind}`}>
      <div className="px-3 py-2 border-b border-[#E6E6E6] flex items-center gap-2">
        <span className="text-[10px] uppercase font-bold text-[#747480]">Artifact</span>
        <span className="text-[11px] font-mono">v{artifact.version}</span>
        <span className="text-[10px] text-[#747480]">{files.length} file(s)</span>
        {artifact.frozen && <span className="text-[9px] uppercase bg-[#FFE600] text-[#2E2E38] font-bold px-1.5 py-0.5 rounded-sm flex items-center gap-1"><Lock className="w-2.5 h-2.5" /> Frozen</span>}
        <div className="ml-auto flex gap-1">
          {!artifact.frozen && (editing ? (
            <>
              <button onClick={() => setEditing(false)} className="text-[11px] px-2 py-1 border border-[#E6E6E6] rounded-sm">Cancel</button>
              <button onClick={onSave} data-testid={`save-${kind}`} className="text-[11px] px-2 py-1 bg-[#2E2E38] text-white rounded-sm">Save</button>
            </>
          ) : (
            <button onClick={() => setEditing(true)} data-testid={`edit-${kind}`} className="text-[11px] px-2 py-1 border border-[#E6E6E6] hover:bg-[#F6F6FA] rounded-sm">Edit</button>
          ))}
          {!artifact.frozen && <button onClick={onFreeze} data-testid={`freeze-${kind}`} className="text-[11px] px-2 py-1 bg-[#2E2E38] text-white rounded-sm flex items-center gap-1"><Lock className="w-3 h-3" /> Freeze</button>}
          <a href={downloadLivingArtifactUrl(projectId, artifact.id)} data-testid={`download-${kind}`} className="text-[11px] px-2 py-1 border border-[#E6E6E6] hover:bg-[#F6F6FA] rounded-sm flex items-center gap-1"><Download className="w-3 h-3" /></a>
        </div>
      </div>
      <div className="grid grid-cols-12 min-h-[420px]">
        {files.length > 1 && (
          <div className="col-span-3 border-r border-[#E6E6E6] overflow-y-auto max-h-[600px]">
            {files.map((f, i) => (
              <button
                key={i}
                onClick={() => setOpenIdx(i)}
                data-testid={`file-tab-${kind}-${i}`}
                className={`w-full text-left text-[11px] font-mono px-2 py-1 border-l-2 truncate ${openIdx === i ? "border-[#FFE600] bg-[#FFFCE6]" : "border-transparent hover:bg-[#F6F6FA]"}`}
              >
                {f.path}
              </button>
            ))}
          </div>
        )}
        <div className={`${files.length > 1 ? "col-span-9" : "col-span-12"} overflow-y-auto max-h-[600px]`}>
          {files[openIdx] && (editing ? (
            <textarea
              value={files[openIdx].content || ""}
              onChange={(e) => {
                const next = [...editFiles]; next[openIdx] = { ...next[openIdx], content: e.target.value };
                setEditFiles(next);
              }}
              className="w-full h-[420px] p-3 font-mono text-[12px] outline-none resize-none"
              spellCheck={false}
              data-testid={`edit-textarea-${kind}`}
            />
          ) : isMarkdownKind ? (
            <div className="prose prose-sm max-w-none p-4 text-[#2E2E38]">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{files[openIdx].content || ""}</ReactMarkdown>
            </div>
          ) : (
            <pre className="p-3 font-mono text-[12px] whitespace-pre-wrap text-[#2E2E38]">{files[openIdx].content}</pre>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function LivingPage() {
  const navigate = useNavigate();
  const { active } = useProjects();
  const projectId = active?.id;
  const status = active?.stage_status?.["Living"] || "locked";
  const cgStatus = active?.stage_status?.["CodeGen"] || "locked";
  const isLocked = cgStatus !== "frozen";
  const isFrozen = status === "frozen";

  const [tab, setTab] = useState("selenium");
  const [artifacts, setArtifacts] = useState([]);
  const [resetOpen, setResetOpen] = useState(false);
  const [activeArtifact, setActiveArtifact] = useState(null);

  // Drift signals editor + SRS-diff inputs
  const [liveSignals, setLiveSignals] = useState("");
  const [srsA, setSrsA] = useState("");
  const [srsB, setSrsB] = useState("");

  const refresh = useCallback(async () => {
    if (!projectId) return;
    try {
      const r = await listLivingArtifacts(projectId);
      setArtifacts(r.artifacts || []);
      const cur = (r.artifacts || []).find((a) => a.kind === tab);
      if (cur) {
        const full = await getLivingArtifact(projectId, cur.id);
        setActiveArtifact(full);
      } else { setActiveArtifact(null); }
    } catch { /* */ }
  }, [projectId, tab]);
  useEffect(() => { refresh(); }, [refresh]);

  const seleniumJob = useJob(getLivingJob, refresh);
  const jmeterJob = useJob(getLivingJob, refresh);
  const driftJob = useJob(getLivingJob, refresh);
  const diffJob = useJob(getLivingJob, refresh);

  const onGenerate = async (kind) => {
    if (!projectId) return;
    try {
      const extras = {};
      if (kind === "drift") extras.live_signals = liveSignals;
      if (kind === "srs-diff") { extras.srs_a = srsA; extras.srs_b = srsB; }
      const r = await startLivingJob(kind, projectId, extras);
      if (kind === "selenium") seleniumJob.start(r.job_id);
      else if (kind === "jmeter") jmeterJob.start(r.job_id);
      else if (kind === "drift") driftJob.start(r.job_id);
      else if (kind === "srs-diff") diffJob.start(r.job_id);
      toast.message(`${kind} job started`);
    } catch (e) { toast.error(`Could not start ${kind}: ` + (e?.response?.data?.detail || e.message)); }
  };

  const onFreezeStage = async () => {
    try { await freezeLiving(projectId); toast.success("Living frozen"); }
    catch { toast.error("Freeze failed"); }
  };
  const onReset = async () => {
    try { await resetLiving(projectId); toast.success("Stage 5 reset"); setResetOpen(false); setArtifacts([]); setActiveArtifact(null); }
    catch { toast.error("Reset failed"); }
  };

  if (!projectId) return <div className="p-8 text-[#747480] text-sm">No active project.</div>;

  if (isLocked) {
    return (
      <div className="flex-1 flex flex-col bg-[#F6F6FA]" data-testid="living-locked">
        <header className="bg-white border-b-2 border-[#FFE600] px-6 py-3">
          <div className="text-[10px] uppercase tracking-widest text-[#747480]">Stage 5 of 5</div>
          <h1 className="font-display text-lg font-bold tracking-tight text-[#2E2E38]">Living System</h1>
        </header>
        <div className="flex-1 flex items-center justify-center p-8">
          <div className="max-w-md bg-white border border-[#E6E6E6] rounded-sm p-6 text-center">
            <Lock className="w-8 h-8 mx-auto text-[#747480] mb-3" />
            <h2 className="font-display font-bold text-[#2E2E38]">Locked — CodeGen not frozen</h2>
            <p className="text-xs text-[#747480] mt-2">Generate code and freeze Stage 4 to unlock Living.</p>
            <button onClick={() => navigate("/code-gen")} className="mt-4 text-xs px-3 py-1.5 bg-[#2E2E38] text-white rounded-sm">Open CodeGen →</button>
          </div>
        </div>
        <MiniConsole stage="Living" projectId={projectId} />
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col min-w-0 bg-[#F6F6FA]" data-testid="living-page">
      <header className="bg-white border-b-2 border-[#FFE600] px-6 py-3 flex items-center justify-between">
        <div>
          <div className="text-[10px] uppercase tracking-widest text-[#747480]">Stage 5 of 5</div>
          <h1 className="font-display text-lg font-bold tracking-tight text-[#2E2E38] flex items-center gap-2">
            <Activity className="w-4 h-4 text-[#FFE600]" /> Living System
          </h1>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-[#747480]">{artifacts.length} artifact(s)</span>
          {isFrozen && <span className="text-[10px] uppercase font-bold bg-[#FFE600] text-[#2E2E38] px-2 py-0.5 rounded-sm">Frozen</span>}
          {!isFrozen && artifacts.length > 0 && (
            <Button onClick={onFreezeStage} data-testid="freeze-living-stage" className="h-7 text-[11px] bg-[#2E2E38] text-white">
              <Lock className="w-3 h-3 mr-1" /> Freeze Stage 5
            </Button>
          )}
          <button onClick={() => setResetOpen(true)} data-testid="btn-reset-living" className="text-xs px-2 py-1 border border-orange-300 text-orange-700 hover:bg-orange-50 rounded-sm flex items-center gap-1">
            <RotateCcw className="w-3 h-3" /> Reset
          </button>
        </div>
      </header>

      <div className="border-b border-[#E6E6E6] bg-white flex items-center px-2">
        {TABS.map((t) => {
          const has = artifacts.find((a) => a.kind === t.id);
          return (
            <button
              key={t.id}
              data-testid={`tab-${t.id}`}
              onClick={() => setTab(t.id)}
              className={`flex items-center gap-1 px-3 py-2 text-[12px] border-b-2 ${tab === t.id ? "border-[#FFE600] text-[#2E2E38] font-semibold" : "border-transparent text-[#747480] hover:text-[#2E2E38]"}`}
            >
              <t.icon className="w-3 h-3" /> {t.label}
              {has && <span className="text-[9px] bg-[#F6F6FA] px-1 rounded-sm">v{has.version}</span>}
              {has?.frozen && <Lock className="w-2.5 h-2.5 text-[#FFE600]" />}
            </button>
          );
        })}
      </div>

      <div className="flex-1 overflow-y-auto mos-scroll p-4 space-y-3">
        {/* Generate row */}
        <div className="bg-white border border-[#E6E6E6] rounded-sm p-3 space-y-2">
          {tab === "selenium" && (
            <div className="flex items-center justify-between gap-3">
              <div className="text-[11px] text-[#747480]">Generate JUnit5 + Selenium WebDriver tests with Page Object Model, one file per use case. Output: ZIP of Java files.</div>
              <Button onClick={() => onGenerate("selenium")} disabled={!!seleniumJob.job && seleniumJob.job.status !== "complete" && seleniumJob.job.status !== "error"} data-testid="btn-gen-selenium" className="h-8 text-[11px] bg-[#FFE600] text-[#2E2E38] hover:bg-[#FFD500]">
                {seleniumJob.job && seleniumJob.job.status === "running" ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <Wand2 className="w-3 h-3 mr-1" />} Generate Selenium
              </Button>
            </div>
          )}
          {tab === "jmeter" && (
            <div className="flex items-center justify-between gap-3">
              <div className="text-[11px] text-[#747480]">Generate Apache JMeter (.jmx) performance test plans with 3 personas (anonymous, authenticated, admin), CSV-driven payloads, and InfluxDB/Grafana backend listener.</div>
              <Button onClick={() => onGenerate("jmeter")} disabled={!!jmeterJob.job && jmeterJob.job.status === "running"} data-testid="btn-gen-jmeter" className="h-8 text-[11px] bg-[#FFE600] text-[#2E2E38] hover:bg-[#FFD500]">
                {jmeterJob.job && jmeterJob.job.status === "running" ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <Wand2 className="w-3 h-3 mr-1" />} Generate JMeter
              </Button>
            </div>
          )}
          {tab === "drift" && (
            <>
              <div className="text-[11px] text-[#747480]">Paste signals from your live system (logs, route inventory, telemetry, schema introspection). LAMA will compare these against the frozen SRS and produce a P0/P1/P2 drift report.</div>
              <textarea
                value={liveSignals} onChange={(e) => setLiveSignals(e.target.value)}
                placeholder="POST /api/orders responded with 503 12% of the time…&#10;GET /api/users — not present in deployed routes…&#10;dim_customer column 'tier' added on 2026-04-22…"
                data-testid="drift-signals-input"
                className="w-full h-32 border border-[#E6E6E6] focus:border-[#2E2E38] outline-none rounded-sm p-2 font-mono text-[11px] resize-y"
              />
              <div className="flex justify-end">
                <Button onClick={() => onGenerate("drift")} disabled={!liveSignals.trim() || (driftJob.job && driftJob.job.status === "running")} data-testid="btn-gen-drift" className="h-8 text-[11px] bg-[#FFE600] text-[#2E2E38] hover:bg-[#FFD500]">
                  {driftJob.job && driftJob.job.status === "running" ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <Wand2 className="w-3 h-3 mr-1" />} Generate Drift Report
                </Button>
              </div>
            </>
          )}
          {tab === "srs_diff" && (
            <>
              <div className="text-[11px] text-[#747480]">Paste two SRS versions (or copy from the Discovery panel). The diff identifies added/removed/modified requirements + which downstream artifacts to regenerate.</div>
              <div className="grid grid-cols-2 gap-2">
                <textarea value={srsA} onChange={(e) => setSrsA(e.target.value)} placeholder="SRS A (e.g. frozen v1)" data-testid="srs-a-input" className="h-32 border border-[#E6E6E6] focus:border-[#2E2E38] outline-none rounded-sm p-2 font-mono text-[11px] resize-y" />
                <textarea value={srsB} onChange={(e) => setSrsB(e.target.value)} placeholder="SRS B (e.g. current draft)" data-testid="srs-b-input" className="h-32 border border-[#E6E6E6] focus:border-[#2E2E38] outline-none rounded-sm p-2 font-mono text-[11px] resize-y" />
              </div>
              <div className="flex justify-end">
                <Button onClick={() => onGenerate("srs-diff")} disabled={!srsA.trim() || !srsB.trim() || (diffJob.job && diffJob.job.status === "running")} data-testid="btn-gen-srs-diff" className="h-8 text-[11px] bg-[#FFE600] text-[#2E2E38] hover:bg-[#FFD500]">
                  {diffJob.job && diffJob.job.status === "running" ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <Wand2 className="w-3 h-3 mr-1" />} Diff SRS
                </Button>
              </div>
            </>
          )}
          <ProgressBar job={tab === "selenium" ? seleniumJob.job : tab === "jmeter" ? jmeterJob.job : tab === "drift" ? driftJob.job : diffJob.job} label={tab} />
        </div>

        <ArtifactPanel kind={tab} artifact={activeArtifact} projectId={projectId} onRefresh={refresh} />
      </div>

      <ResetModal open={resetOpen} onClose={() => setResetOpen(false)} onConfirm={onReset} />
      <MiniConsole stage="Living" projectId={projectId} />
    </div>
  );
}
