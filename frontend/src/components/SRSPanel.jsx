import React, { useEffect, useState, useCallback } from "react";
import { FileDown, Lock, Unlock, RefreshCw, Sparkles, Loader2 } from "lucide-react";
import { getSRS, updateSRSSection, freezeSRS, unfreezeSRS, srsPdfUrl, API } from "@/lib/api";
import HelpIcon from "@/components/HelpIcon";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

const SECTIONS = [
  { key: "purpose", label: "1. Purpose" },
  { key: "scope", label: "2. Scope" },
  { key: "definitions", label: "3. Definitions, Acronyms & Abbreviations" },
  { key: "overall_description", label: "4. Overall Description" },
  { key: "functional_requirements", label: "5. Functional Requirements" },
  { key: "non_functional_requirements", label: "6. Non-Functional Requirements" },
  { key: "use_cases", label: "7. Use Cases" },
  { key: "constraints", label: "8. Constraints" },
];

export default function SRSPanel({ projectId, conversationId, kbReady, onFrozen }) {
  const [srs, setSrs] = useState(null);
  const [busy, setBusy] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [progress, setProgress] = useState({ index: 0, total: 8, label: "" });
  const [doneSections, setDoneSections] = useState(new Set());

  const refresh = useCallback(async () => {
    if (!projectId) return;
    const data = await getSRS(projectId);
    setSrs(data);
  }, [projectId]);

  useEffect(() => { refresh(); }, [refresh]);

  const handleGenerate = async () => {
    if (!projectId) return;
    setGenerating(true);
    setDoneSections(new Set());
    setProgress({ index: 0, total: 8, label: "Starting…" });
    try {
      const res = await fetch(`${API}/srs/generate/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
        body: JSON.stringify({ project_id: projectId, conversation_id: conversationId }),
      });
      if (!res.ok || !res.body) {
        const detail = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(detail.detail || `HTTP ${res.status}`);
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      // Initialise sections object so progressive UI works
      setSrs((s) => ({ ...(s || { project_id: projectId, version: 0 }), sections: { ...(s?.sections || {}) }, frozen: false }));
      // eslint-disable-next-line no-constant-condition
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const events = buf.split("\n\n");
        buf = events.pop() || "";
        for (const evt of events) {
          const line = evt.split("\n").find((l) => l.startsWith("data:"));
          if (!line) continue;
          let data;
          try { data = JSON.parse(line.slice(5).trim()); } catch { continue; }
          if (data.type === "section_start") {
            setProgress({ index: data.index, total: data.total, label: data.label });
          } else if (data.type === "section_complete") {
            setSrs((s) => ({ ...(s || {}), sections: { ...(s?.sections || {}), [data.section]: data.content } }));
            setDoneSections((d) => { const n = new Set(d); n.add(data.section); return n; });
          } else if (data.type === "complete") {
            setProgress({ index: data.total || 8, total: data.total || 8, label: "Complete" });
            toast.success(`SRS v${data.version} generated`, { description: `${(data.total_tokens || 0).toLocaleString()} tokens used` });
          }
        }
      }
      await refresh();
    } catch (e) {
      toast.error("SRS generation failed", { description: e.message });
    } finally {
      setGenerating(false);
    }
  };

  const handleSection = async (key, content) => {
    if (!srs || srs.frozen) return;
    setSrs((s) => ({ ...s, sections: { ...s.sections, [key]: content } }));
    try {
      await updateSRSSection(projectId, key, content);
    } catch (e) {
      toast.error("Save failed", { description: e.message });
    }
  };

  const handleFreeze = async () => {
    setBusy(true);
    try {
      await freezeSRS(projectId, "current-user");
      toast.success("SRS frozen");
      await refresh();
      onFrozen?.();
    } catch (e) {
      toast.error("Freeze failed", { description: e.message });
    } finally {
      setBusy(false);
    }
  };

  const handleUnfreeze = async () => {
    setBusy(true);
    try {
      await unfreezeSRS(projectId);
      toast.success("SRS unlocked");
      await refresh();
    } catch (e) {
      toast.error("Unfreeze failed", { description: e.message });
    } finally {
      setBusy(false);
    }
  };

  const handleExport = () => {
    if (!projectId) return;
    window.open(srsPdfUrl(projectId), "_blank");
  };

  const frozen = !!srs?.frozen;
  const hasContent = srs?.sections && Object.values(srs.sections).some((v) => v && v.trim());

  return (
    <div className="h-full flex flex-col mos-panel min-h-0">
      {/* Header */}
      <div className="px-4 py-3 border-b border-slate-200 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="font-display text-sm font-bold tracking-tight">IEEE 830 SRS</h3>
          <HelpIcon text="Live preview of the Software Requirements Specification. Edit any section inline. Freeze to lock and advance the pipeline." testId="help-srs" />
          {frozen && <span className="text-[10px] uppercase tracking-wider bg-emerald-100 text-emerald-700 px-1.5 py-0.5 rounded-sm">Frozen v{srs?.version}</span>}
          {!frozen && hasContent && <span className="text-[10px] uppercase tracking-wider bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded-sm">Draft v{srs?.version}</span>}
        </div>
        <div className="flex items-center gap-1.5">
          <Button
            data-testid="generate-srs-btn"
            variant="secondary"
            size="sm"
            onClick={handleGenerate}
            disabled={generating || frozen || !kbReady}
            className="bg-white border border-slate-300 hover:bg-slate-50 text-slate-700 rounded-sm text-xs h-8"
          >
            {generating ? <RefreshCw className="w-3.5 h-3.5 mr-1 animate-spin" /> : <Sparkles className="w-3.5 h-3.5 mr-1" />}
            {hasContent ? "Regenerate" : "Generate"}
          </Button>
          <Button
            data-testid="export-pdf-btn"
            variant="secondary"
            size="sm"
            onClick={handleExport}
            disabled={!hasContent}
            className="bg-white border border-slate-300 hover:bg-slate-50 text-slate-700 rounded-sm text-xs h-8"
          >
            <FileDown className="w-3.5 h-3.5 mr-1" />
            PDF
          </Button>
          {frozen ? (
            <Button
              data-testid="unfreeze-btn"
              size="sm"
              onClick={handleUnfreeze}
              disabled={busy}
              className="bg-white border border-amber-300 text-amber-700 hover:bg-amber-50 rounded-sm text-xs h-8"
            >
              <Unlock className="w-3.5 h-3.5 mr-1" /> Unfreeze
            </Button>
          ) : (
            <Button
              data-testid="freeze-btn"
              size="sm"
              onClick={handleFreeze}
              disabled={busy || !hasContent}
              className="bg-[#0A2540] text-white hover:bg-[#021122] rounded-sm text-xs h-8"
            >
              <Lock className="w-3.5 h-3.5 mr-1" /> Freeze SRS
            </Button>
          )}
        </div>
      </div>

      {/* Progress bar (during streaming generation) */}
      {generating && (
        <div className="px-4 py-3 border-b border-slate-200 bg-amber-50" data-testid="srs-progress">
          <div className="flex items-center justify-between text-xs">
            <div className="flex items-center gap-2 text-amber-900 font-semibold">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              {progress.label || "Starting…"}
            </div>
            <div className="text-amber-800 font-mono">{progress.index}/{progress.total}</div>
          </div>
          <div className="mt-2 h-1.5 bg-amber-200 rounded-sm overflow-hidden">
            <div
              className="h-full bg-[#0A2540]"
              style={{ width: `${(progress.index / progress.total) * 100}%` }}
              data-testid="srs-progress-bar"
            />
          </div>
        </div>
      )}

      {/* Body */}
      <div className="flex-1 overflow-y-auto mos-scroll bg-slate-50">
        <div className="max-w-3xl mx-auto p-6">
          <div className="bg-white border border-slate-300 shadow-sm rounded-sm p-8">
            <div className="border-b border-slate-200 pb-3 mb-4">
              <div className="text-[10px] uppercase tracking-widest text-slate-500">Software Requirements Specification</div>
              <h1 className="font-display text-2xl font-bold tracking-tight text-[#0A2540] mt-1">
                {srs?.project_id ? `Migration SRS · v${srs?.version || 0}` : "—"}
              </h1>
              {frozen && (
                <div className="text-[11px] text-slate-500 mt-1">
                  Frozen on {new Date(srs.frozen_at).toLocaleString()} by {srs.frozen_by}
                </div>
              )}
            </div>

            {!hasContent && !generating && (
              <div className="text-center py-16 text-slate-500">
                <Sparkles className="w-6 h-6 mx-auto mb-2 text-slate-400" />
                <div className="text-sm">No SRS yet. Have a discovery conversation, then click <b>Generate</b>.</div>
              </div>
            )}

            {(hasContent || generating) && SECTIONS.map((s) => {
              const isDone = doneSections.has(s.key);
              const isCurrent = generating && progress.label.startsWith(s.label);
              const content = srs?.sections?.[s.key];
              return (
                <section key={s.key} className="mb-8" data-testid={`srs-section-${s.key}`}>
                  <div className="flex items-center justify-between mb-2">
                    <h2 className="font-display text-base font-bold text-[#0A2540] tracking-tight">{s.label}</h2>
                    {generating && (
                      isDone ? <span className="text-[10px] uppercase tracking-wider bg-emerald-100 text-emerald-700 px-1.5 py-0.5 rounded-sm">Done</span>
                      : isCurrent ? <span className="text-[10px] uppercase tracking-wider bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded-sm flex items-center"><Loader2 className="w-2.5 h-2.5 mr-1 animate-spin" />Writing</span>
                      : <span className="text-[10px] uppercase tracking-wider bg-slate-100 text-slate-500 px-1.5 py-0.5 rounded-sm">Queued</span>
                    )}
                  </div>
                  <div
                    className="mos-srs-editable text-slate-800 whitespace-pre-wrap"
                    contentEditable={!frozen && !generating}
                    suppressContentEditableWarning
                    onBlur={(e) => !generating && handleSection(s.key, e.currentTarget.innerText)}
                    data-testid={`srs-edit-${s.key}`}
                  >
                    {content || (isCurrent ? "Writing…" : generating ? "Pending — waiting for previous sections" : "(empty)")}
                  </div>
                </section>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
