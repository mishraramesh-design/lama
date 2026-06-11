import React, { useEffect, useMemo, useState, useRef, useCallback } from "react";
import { Link } from "react-router-dom";
import {
  ArrowLeft, Loader2, Cpu, RefreshCw, Save, Trash2, Plus,
  Shield, CreditCard, Database, Sparkles, AlertTriangle, CheckCircle2,
} from "lucide-react";
import { toast } from "sonner";
import { useProjects } from "@/state/ProjectContext";
import {
  getIndiaStackCatalog, getIndiaStackSelections, saveIndiaStackSelections,
  generateIndiaStackCode, getIndiaStackServices,
} from "@/lib/api";
import { Button } from "@/components/ui/button";

const CATEGORY_META = {
  Identity:    { icon: Shield, color: "#2563EB", bg: "#DBEAFE" },
  Payments:    { icon: CreditCard, color: "#059669", bg: "#D1FAE5" },
  DataSharing: { icon: Database, color: "#9D174D", bg: "#FCE7F3" },
};

function PaletteCard({ component, onDragStart, isSelected }) {
  const meta = CATEGORY_META[component.category] || CATEGORY_META.Identity;
  const Icon = meta.icon;
  return (
    <div draggable onDragStart={(e) => onDragStart(e, component)}
      data-testid={`palette-${component.id}`}
      className={`p-3 border rounded-sm cursor-move transition mb-2
                  ${isSelected ? "opacity-40" : "hover:shadow-md"}`}
      style={{ borderColor: meta.color, background: meta.bg + "55" }}>
      <div className="flex items-start gap-2">
        <div className="rounded-sm p-1.5" style={{ background: meta.bg }}>
          <Icon className="w-4 h-4" style={{ color: meta.color }} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="font-bold text-[13px] text-[#2E2E38] leading-tight">{component.name}</div>
          <div className="text-[10px] text-[#747480] mt-0.5 line-clamp-2">{component.description}</div>
          <div className="flex flex-wrap gap-1 mt-1.5">
            <span className="text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded-sm"
              style={{ background: meta.color, color: "white" }}>{component.category}</span>
            <span className="text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded-sm bg-[#2E2E38] text-white">
              {component.scope}
            </span>
            <span className="text-[9px] text-[#747480]">{component.endpoints.length} endpoints</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function DropTarget({ service, selections, catalog, onDrop, onRemove, onUpdate }) {
  const [over, setOver] = useState(false);
  const selsHere = selections.filter((s) => s.attach_to === service.name);
  const isNew = service.name === "new";
  return (
    <div
      data-testid={`drop-target-${service.name}`}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); onDrop(e, service.name); }}
      className={`border-2 border-dashed rounded-sm p-3 mb-2 transition-all
                  ${over ? "border-[#FFE600] bg-[#FFFCE6]" :
                           isNew ? "border-[#9CA3AF] bg-white" : "border-[#E6E6E6] bg-white"}`}>
      <div className="flex items-center justify-between mb-2">
        <div className="font-bold text-[13px] text-[#2E2E38]">
          {isNew ? "+ Create new microservice" : service.display_name}
        </div>
        <span className="text-[10px] text-[#747480]">{selsHere.length} attached</span>
      </div>
      <div className="text-[10px] text-[#747480] mb-2">
        {isNew
          ? "Dropping here makes a brand-new microservice per component."
          : `Drop components to add their code to ${service.display_name}.`}
      </div>
      {selsHere.length === 0 ? (
        <div className="text-[10px] italic text-[#9CA3AF] py-3 text-center">
          (drag a component here)
        </div>
      ) : (
        <div className="space-y-1.5">
          {selsHere.map((s) => {
            const cat = catalog.find((c) => c.id === s.component_id);
            if (!cat) return null;
            const meta = CATEGORY_META[cat.category] || CATEGORY_META.Identity;
            return (
              <div key={s.component_id}
                data-testid={`attached-${service.name}-${s.component_id}`}
                className="border border-[#E6E6E6] rounded-sm p-2 bg-[#FAFAFC]">
                <div className="flex items-center gap-2 mb-1">
                  <span className="w-2 h-2 rounded-full" style={{ background: meta.color }} />
                  <span className="font-bold text-[12px] text-[#2E2E38] flex-1">{cat.name}</span>
                  <button onClick={() => onRemove(s.component_id)}
                    data-testid={`remove-${s.component_id}`}
                    className="text-[#747480] hover:text-rose-600">
                    <Trash2 className="w-3 h-3" />
                  </button>
                </div>
                <div className="flex flex-wrap gap-1 items-center">
                  <label className="text-[9px] uppercase tracking-wider text-[#747480]">Mode</label>
                  <select value={s.mode || "mock"}
                    onChange={(e) => onUpdate(s.component_id, { mode: e.target.value })}
                    data-testid={`mode-${s.component_id}`}
                    className="text-[10px] border border-[#E6E6E6] rounded-sm px-1 py-0.5">
                    <option value="mock">Mock stub</option>
                    <option value="sandbox">Real sandbox</option>
                  </select>
                  {s.mode === "sandbox" && cat.sandbox_providers.length > 0 && (
                    <select value={s.sandbox_provider || cat.sandbox_providers[0]}
                      onChange={(e) => onUpdate(s.component_id, { sandbox_provider: e.target.value })}
                      data-testid={`provider-${s.component_id}`}
                      className="text-[10px] border border-[#E6E6E6] rounded-sm px-1 py-0.5">
                      {cat.sandbox_providers.map((p) => <option key={p} value={p}>{p}</option>)}
                    </select>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function IndiaStackPage() {
  const { active } = useProjects();
  const projectId = active?.id;
  const [catalog, setCatalog] = useState([]);
  const [selections, setSelections] = useState([]);
  const [services, setServices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [filterCat, setFilterCat] = useState("All");

  const dragRef = useRef(null);

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const [c, s, svc] = await Promise.all([
        getIndiaStackCatalog(),
        getIndiaStackSelections(projectId),
        getIndiaStackServices(projectId),
      ]);
      setCatalog(c.components || []);
      setSelections(s.selections || []);
      setServices(svc.services || []);
    } catch (e) {
      toast.error("Failed to load India-Stack data", { description: e.message });
    } finally { setLoading(false); }
  }, [projectId]);

  useEffect(() => { load(); }, [load]);

  const onDragStart = (e, component) => {
    dragRef.current = component;
    e.dataTransfer.effectAllowed = "copy";
  };
  const onDrop = (e, serviceName) => {
    const comp = dragRef.current;
    if (!comp) return;
    setSelections((prev) => {
      const without = prev.filter((s) => s.component_id !== comp.id);
      return [...without, {
        component_id: comp.id,
        attach_to: serviceName,
        mode: "mock",
        sandbox_provider: comp.sandbox_providers[0] || "",
        env: {},
      }];
    });
    dragRef.current = null;
  };
  const onRemove = (componentId) =>
    setSelections((prev) => prev.filter((s) => s.component_id !== componentId));
  const onUpdate = (componentId, patch) =>
    setSelections((prev) => prev.map((s) =>
      s.component_id === componentId ? { ...s, ...patch } : s));

  const saveAndGenerate = async (genAfter = false) => {
    if (!projectId) return;
    setSaving(true);
    try {
      await saveIndiaStackSelections(projectId, selections);
      toast.success(`Saved ${selections.length} selection${selections.length === 1 ? "" : "s"}`);
      if (genAfter) {
        setGenerating(true);
        const r = await generateIndiaStackCode(projectId);
        toast.success(`Generated ${r.count} files — view in Stage 4 (CodeGen)`);
      }
    } catch (e) {
      toast.error("Save / generate failed", { description: e.response?.data?.detail || e.message });
    } finally { setSaving(false); setGenerating(false); }
  };

  const filteredCatalog = useMemo(() => filterCat === "All"
    ? catalog : catalog.filter((c) => c.category === filterCat),
  [catalog, filterCat]);
  const selectedIds = useMemo(() => new Set(selections.map((s) => s.component_id)), [selections]);

  if (!projectId) {
    return <div className="p-8 text-[#747480]" data-testid="india-stack-no-project">No active project.</div>;
  }
  if (loading) {
    return <div className="p-8 flex items-center gap-2 text-[#747480]" data-testid="india-stack-loading">
      <Loader2 className="w-4 h-4 animate-spin" /> Loading India-Stack…</div>;
  }

  return (
    <div className="flex-1 flex flex-col min-w-0 bg-[#F6F6FA]" data-testid="india-stack-page">
      <header className="bg-white border-b-2 border-[#FFE600] px-6 py-3 flex items-center justify-between">
        <div>
          <Link to="/architecture" data-testid="back-to-arch"
            className="text-[10px] uppercase tracking-widest text-[#747480] flex items-center gap-1 hover:text-[#2E2E38]">
            <ArrowLeft className="w-3 h-3" /> Back to Architecture
          </Link>
          <h1 className="font-display text-lg font-bold tracking-tight text-[#2E2E38] flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-[#FFE600]" /> India Stack Decisions
          </h1>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-[#747480]" data-testid="selection-count">
            {selections.length} selected
          </span>
          <Button onClick={() => saveAndGenerate(false)} disabled={saving}
            variant="outline" className="h-7 text-[11px]" data-testid="save-btn">
            {saving ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <Save className="w-3 h-3 mr-1" />} Save
          </Button>
          <Button onClick={() => saveAndGenerate(true)} disabled={saving || generating || selections.length === 0}
            className="h-7 text-[11px] bg-[#FFE600] text-[#2E2E38] hover:bg-[#FFD500] font-bold"
            data-testid="generate-btn">
            {generating ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <Cpu className="w-3 h-3 mr-1" />}
            Save & Generate Code
          </Button>
        </div>
      </header>

      <div className="flex-1 min-h-0 grid grid-cols-12 overflow-hidden">
        {/* Palette */}
        <div className="col-span-4 border-r border-[#E6E6E6] overflow-y-auto p-3 bg-white" data-testid="palette">
          <div className="flex items-center justify-between mb-2">
            <h2 className="font-bold text-[12px] uppercase tracking-wider text-[#2E2E38]">Catalog</h2>
            <select value={filterCat} onChange={(e) => setFilterCat(e.target.value)}
              data-testid="catalog-filter"
              className="text-[10px] border border-[#E6E6E6] rounded-sm px-1 py-0.5">
              <option>All</option><option>Identity</option><option>Payments</option><option>DataSharing</option>
            </select>
          </div>
          <div className="text-[10px] text-[#747480] mb-3">
            Drag a component into a microservice on the right.
          </div>
          {filteredCatalog.map((c) =>
            <PaletteCard key={c.id} component={c}
              onDragStart={onDragStart}
              isSelected={selectedIds.has(c.id)} />)}
        </div>

        {/* Drop zones */}
        <div className="col-span-8 overflow-y-auto p-4" data-testid="drop-zones">
          <h2 className="font-bold text-[12px] uppercase tracking-wider text-[#2E2E38] mb-2">
            Architecture targets
          </h2>
          <div className="text-[10px] text-[#747480] mb-3">
            Existing services + a &quot;create new&quot; zone. India-Stack code will attach to whichever target you drop on.
          </div>
          {services.map((svc) =>
            <DropTarget key={svc.name} service={svc}
              selections={selections} catalog={catalog}
              onDrop={onDrop} onRemove={onRemove} onUpdate={onUpdate} />)}
          {services.length === 1 && (
            <div className="bg-amber-50 border border-amber-200 rounded-sm p-2 text-[11px] text-amber-800 flex items-center gap-2">
              <AlertTriangle className="w-3 h-3" />
              You have no architecture services yet. Run Stage 3 (Architecture) HLD first to get drop targets — or
              leave everything on &quot;+ New microservice&quot; and code-gen will scaffold them.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
