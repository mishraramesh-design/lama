import React, { useEffect, useState, useCallback } from "react";
import { FileDown, Lock, Unlock, RefreshCw, Sparkles } from "lucide-react";
import { getSRS, generateSRS, updateSRSSection, freezeSRS, unfreezeSRS, srsPdfUrl } from "@/lib/api";
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

  const refresh = useCallback(async () => {
    if (!projectId) return;
    const data = await getSRS(projectId);
    setSrs(data);
  }, [projectId]);

  useEffect(() => { refresh(); }, [refresh]);

  const handleGenerate = async () => {
    if (!projectId) return;
    setGenerating(true);
    try {
      await generateSRS(projectId, conversationId);
      toast.success("SRS generated");
      await refresh();
    } catch (e) {
      toast.error("SRS generation failed", { description: e.response?.data?.detail || e.message });
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

            {(hasContent || generating) && SECTIONS.map((s) => (
              <section key={s.key} className="mb-6" data-testid={`srs-section-${s.key}`}>
                <h2 className="font-display text-base font-bold text-[#0A2540] mb-2 tracking-tight">{s.label}</h2>
                <div
                  className="mos-srs-editable text-slate-800"
                  contentEditable={!frozen}
                  suppressContentEditableWarning
                  onBlur={(e) => handleSection(s.key, e.currentTarget.innerText)}
                  data-testid={`srs-edit-${s.key}`}
                >
                  {srs?.sections?.[s.key] || (generating ? "Generating…" : "(empty)")}
                </div>
              </section>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
