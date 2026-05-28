import React, { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import {
  ArrowLeft, Loader2, Network, ListTree, Search, Download,
  ZoomIn, ZoomOut, RotateCcw, Filter, Boxes, RefreshCw,
  Users, Database, FileCode, Tag, Building2, AlertTriangle,
} from "lucide-react";
import { toast } from "sonner";
import { useProjects } from "@/state/ProjectContext";
import {
  getBusinessOntology, startBusinessOntologyJob, getBusinessOntologyJob,
} from "@/lib/api";
import { Button } from "@/components/ui/button";

// ────────────────────────────────────────────────────────────────────
// A consistent yellow-accented palette per domain bucket
// ────────────────────────────────────────────────────────────────────
const DOMAIN_PALETTE = [
  { bg: "#FFFCE6", border: "#CCB800", color: "#2E2E38" },
  { bg: "#E0F2FE", border: "#0284C7", color: "#0369A1" },
  { bg: "#D1FAE5", border: "#059669", color: "#065F46" },
  { bg: "#FCE7F3", border: "#BE185D", color: "#9D174D" },
  { bg: "#F3EFFF", border: "#7C3AED", color: "#5B21B6" },
  { bg: "#FEF3C7", border: "#B45309", color: "#92400E" },
  { bg: "#FEE2E2", border: "#B91C1C", color: "#7F1D1D" },
  { bg: "#F3F4F6", border: "#9CA3AF", color: "#374151" },
];

function paletteForDomains(domains) {
  const out = {};
  domains.forEach((d, i) => { out[d] = DOMAIN_PALETTE[i % DOMAIN_PALETTE.length]; });
  return out;
}

// ────────────────────────────────────────────────────────────────────
// Force-directed layout (kept lightweight — business ontologies are
// typically 15-40 entities so iter=60 stays well under 100ms.)
// ────────────────────────────────────────────────────────────────────
function forceLayout(nodes, edges, { width = 1400, height = 900, iter = 60 } = {}) {
  if (!nodes.length) return [];
  const N = nodes.length;
  if (N > 200) iter = 30;
  const k = Math.sqrt((width * height) / N) * 0.85;
  const positioned = nodes.map((n) => ({
    ...n,
    x: width / 2 + (Math.random() - 0.5) * width * 0.6,
    y: height / 2 + (Math.random() - 0.5) * height * 0.6,
    dx: 0, dy: 0,
  }));
  const byId = Object.fromEntries(positioned.map((n) => [n.id, n]));
  let t = width / 10;
  for (let step = 0; step < iter; step++) {
    for (const a of positioned) { a.dx = 0; a.dy = 0; }
    for (let i = 0; i < N; i++) {
      for (let j = i + 1; j < N; j++) {
        const a = positioned[i], b = positioned[j];
        const dx = a.x - b.x, dy = a.y - b.y;
        const d = Math.sqrt(dx * dx + dy * dy) || 0.01;
        const f = (k * k) / d;
        const fx = (dx / d) * f, fy = (dy / d) * f;
        a.dx += fx; a.dy += fy;
        b.dx -= fx; b.dy -= fy;
      }
    }
    for (const e of edges) {
      const a = byId[e.source], b = byId[e.target];
      if (!a || !b) continue;
      const dx = a.x - b.x, dy = a.y - b.y;
      const d = Math.sqrt(dx * dx + dy * dy) || 0.01;
      const f = (d * d) / k;
      const fx = (dx / d) * f, fy = (dy / d) * f;
      a.dx -= fx; a.dy -= fy;
      b.dx += fx; b.dy += fy;
    }
    for (const a of positioned) {
      const disp = Math.sqrt(a.dx * a.dx + a.dy * a.dy) || 0.01;
      a.x += (a.dx / disp) * Math.min(disp, t);
      a.y += (a.dy / disp) * Math.min(disp, t);
      a.x = Math.max(80, Math.min(width - 80, a.x));
      a.y = Math.max(60, Math.min(height - 60, a.y));
    }
    t = Math.max(t * 0.9, 1);
  }
  return positioned;
}

// ────────────────────────────────────────────────────────────────────
// Graph view
// ────────────────────────────────────────────────────────────────────
function GraphView({ entities, relationships, search, activeDomains, palette, onSelect, selected }) {
  const svgRef = useRef(null);
  const [view, setView] = useState({ scale: 1, tx: 0, ty: 0 });
  const dragRef = useRef(null);

  const filteredEntities = useMemo(() => entities.filter((e) =>
    activeDomains.has(e.domain) &&
    (!search || (e.name || "").toLowerCase().includes(search.toLowerCase())
              || (e.description || "").toLowerCase().includes(search.toLowerCase()))
  ), [entities, activeDomains, search]);

  const visibleIds = useMemo(() => new Set(filteredEntities.map((n) => n.id)), [filteredEntities]);
  const filteredRels = useMemo(() => relationships.filter(
    (r) => visibleIds.has(r.source) && visibleIds.has(r.target)
  ), [relationships, visibleIds]);

  const positioned = useMemo(
    () => forceLayout(filteredEntities, filteredRels, { width: 1600, height: 1100 }),
    [filteredEntities, filteredRels]
  );
  const byId = useMemo(() => Object.fromEntries(positioned.map((n) => [n.id, n])), [positioned]);

  const onWheel = useCallback((e) => {
    e.preventDefault();
    const dir = e.deltaY < 0 ? 1.1 : 1 / 1.1;
    setView((v) => ({ ...v, scale: Math.max(0.2, Math.min(4, v.scale * dir)) }));
  }, []);

  const onMouseDown = (e) => {
    if (e.target.dataset && e.target.dataset.node) return;
    dragRef.current = { x: e.clientX, y: e.clientY, tx: view.tx, ty: view.ty };
  };
  const onMouseMove = (e) => {
    if (!dragRef.current) return;
    setView((v) => ({
      ...v,
      tx: dragRef.current.tx + (e.clientX - dragRef.current.x),
      ty: dragRef.current.ty + (e.clientY - dragRef.current.y),
    }));
  };
  const onMouseUp = () => { dragRef.current = null; };

  const isHighlighted = (nid) => {
    if (!selected) return true;
    if (nid === selected) return true;
    return filteredRels.some((r) =>
      (r.source === selected && r.target === nid) ||
      (r.target === selected && r.source === nid)
    );
  };

  return (
    <div className="relative w-full h-full overflow-hidden bg-[#FAFAFC]" data-testid="ontology-graph">
      <div className="absolute top-3 right-3 z-10 flex flex-col gap-1 bg-white border border-[#E6E6E6] rounded-sm shadow-sm">
        <button onClick={() => setView((v) => ({ ...v, scale: Math.min(4, v.scale * 1.2) }))} className="p-1.5 hover:bg-[#F6F6FA]" data-testid="graph-zoom-in"><ZoomIn className="w-3 h-3" /></button>
        <button onClick={() => setView((v) => ({ ...v, scale: Math.max(0.2, v.scale / 1.2) }))} className="p-1.5 hover:bg-[#F6F6FA]" data-testid="graph-zoom-out"><ZoomOut className="w-3 h-3" /></button>
        <button onClick={() => setView({ scale: 1, tx: 0, ty: 0 })} className="p-1.5 hover:bg-[#F6F6FA]" data-testid="graph-reset"><RotateCcw className="w-3 h-3" /></button>
      </div>
      <div className="absolute bottom-3 left-3 z-10 bg-white border border-[#E6E6E6] rounded-sm px-2 py-1 text-[10px] text-[#747480]" data-testid="graph-stats">
        {positioned.length} entities · {filteredRels.length} relationships · zoom {Math.round(view.scale * 100)}%
      </div>
      <svg
        ref={svgRef}
        width="100%" height="100%"
        viewBox="0 0 1600 1100"
        onWheel={onWheel}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={onMouseUp}
        style={{ cursor: dragRef.current ? "grabbing" : "grab" }}
      >
        <defs>
          <marker id="biz-arrow" viewBox="0 -5 10 10" refX="22" refY="0" markerWidth="7" markerHeight="7" orient="auto">
            <path d="M0,-5L10,0L0,5" fill="#2E2E38" />
          </marker>
          <marker id="biz-arrow-fk" viewBox="0 -5 10 10" refX="22" refY="0" markerWidth="7" markerHeight="7" orient="auto">
            <path d="M0,-5L10,0L0,5" fill="#9CA3AF" />
          </marker>
        </defs>
        <g transform={`translate(${view.tx} ${view.ty}) scale(${view.scale})`}>
          {filteredRels.map((r, i) => {
            const a = byId[r.source], b = byId[r.target];
            if (!a || !b) return null;
            const dim = selected && !(a.id === selected || b.id === selected);
            const isFk = (r.kind || "business") === "fk";
            // Midpoint label
            const mx = (a.x + b.x) / 2;
            const my = (a.y + b.y) / 2;
            return (
              <g key={`r${i}`} opacity={dim ? 0.15 : 0.9}>
                <line
                  x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                  stroke={isFk ? "#9CA3AF" : "#2E2E38"}
                  strokeWidth={isFk ? 1 : 1.6}
                  strokeDasharray={isFk ? "4 3" : ""}
                  markerEnd={isFk ? "url(#biz-arrow-fk)" : "url(#biz-arrow)"}
                />
                {r.verb && !dim && (
                  <text x={mx} y={my - 4} textAnchor="middle" fontSize={9}
                    fill={isFk ? "#9CA3AF" : "#2E2E38"}
                    style={{ paintOrder: "stroke", stroke: "#FAFAFC", strokeWidth: 3, strokeLinejoin: "round" }}>
                    {r.verb}
                  </text>
                )}
              </g>
            );
          })}
          {positioned.map((n) => {
            const meta = palette[n.domain] || DOMAIN_PALETTE[0];
            const w = Math.max(80, Math.min(160, (n.name || "").length * 7 + 24));
            const h = 30;
            const hl = isHighlighted(n.id);
            const isSel = n.id === selected;
            return (
              <g key={n.id} data-node={n.id}
                 onClick={(e) => { e.stopPropagation(); onSelect(n); }}
                 style={{ cursor: "pointer" }}
                 opacity={hl ? 1 : 0.25}>
                <rect x={n.x - w / 2} y={n.y - h / 2}
                  rx={6} ry={6} width={w} height={h}
                  fill={meta.bg} stroke={meta.border}
                  strokeWidth={isSel ? 3 : 1.4} />
                <text x={n.x} y={n.y + 4} textAnchor="middle"
                  fontSize={11} fontWeight={600} fill={meta.color}>
                  {(n.name || "").length > 22 ? (n.name || "").slice(0, 22) + "…" : n.name}
                </text>
              </g>
            );
          })}
        </g>
      </svg>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────
// Tree view — group entities by domain
// ────────────────────────────────────────────────────────────────────
function TreeView({ entities, search, activeDomains, palette, onSelect, selected }) {
  const grouped = useMemo(() => {
    const out = {};
    for (const e of entities) {
      if (!activeDomains.has(e.domain)) continue;
      if (search && !(
        (e.name || "").toLowerCase().includes(search.toLowerCase()) ||
        (e.description || "").toLowerCase().includes(search.toLowerCase())
      )) continue;
      out[e.domain] = out[e.domain] || [];
      out[e.domain].push(e);
    }
    Object.values(out).forEach((arr) => arr.sort((a, b) => (a.name || "").localeCompare(b.name || "")));
    return out;
  }, [entities, search, activeDomains]);

  return (
    <div className="overflow-y-auto h-full p-3 bg-white border-r border-[#E6E6E6]" data-testid="ontology-tree">
      {Object.entries(grouped).map(([dom, list]) => {
        const meta = palette[dom] || DOMAIN_PALETTE[0];
        return (
          <div key={dom} className="mb-3">
            <div className="text-[10px] uppercase font-bold mb-1" style={{ color: meta.color }}>
              {dom} <span className="text-[#747480]">({list.length})</span>
            </div>
            <div className="space-y-0.5">
              {list.map((e) => (
                <button key={e.id} onClick={() => onSelect(e)}
                  data-testid={`tree-${e.id}`}
                  className={`w-full text-left text-[11px] px-2 py-1 rounded-sm truncate ${
                    selected === e.id ? "bg-[#FFFCE6] border border-[#FFE600]" : "hover:bg-[#F6F6FA]"
                  }`}
                  style={{ borderLeft: `3px solid ${meta.border}` }}>
                  <span className="font-semibold">{e.name}</span>
                  {e.lifecycle_states && e.lifecycle_states.length > 0 && (
                    <span className="text-[9px] text-[#747480] ml-1">· {e.lifecycle_states.length} states</span>
                  )}
                </button>
              ))}
            </div>
          </div>
        );
      })}
      {Object.keys(grouped).length === 0 && (
        <div className="text-[11px] text-[#747480] py-4">No entities match.</div>
      )}
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────
// Detail panel — full business-entity card
// ────────────────────────────────────────────────────────────────────
function DetailPanel({ entity, relationships, byId, palette, onSelect }) {
  if (!entity) {
    return (
      <div className="p-4 text-[11px] text-[#747480] flex items-center justify-center h-full">
        <div className="text-center">
          <Building2 className="w-6 h-6 mx-auto mb-2 text-[#FFE600]" />
          Click any entity to see its description, source tables, owning role and lifecycle.
        </div>
      </div>
    );
  }
  const meta = palette[entity.domain] || DOMAIN_PALETTE[0];
  const rels = relationships.filter((r) => r.source === entity.id || r.target === entity.id);
  return (
    <div className="p-3 overflow-y-auto h-full bg-white" data-testid={`detail-${entity.id}`}>
      <div className="text-[9px] uppercase font-bold tracking-wider mb-1" style={{ color: meta.color }}>
        {entity.domain}
      </div>
      <div className="font-display font-bold text-[#2E2E38] text-base break-all leading-tight">{entity.name}</div>
      <div className="text-[10px] font-mono text-[#747480] break-all mt-0.5">id: {entity.id}</div>

      {entity.description && (
        <div className="mt-3 text-[11px] text-[#2E2E38] leading-relaxed bg-[#FAFAFC] border-l-2 border-[#FFE600] px-2 py-1.5">
          {entity.description}
        </div>
      )}

      <div className="mt-3 space-y-2">
        {entity.business_owner && (
          <DetailRow icon={Users} label="Business owner" value={entity.business_owner} />
        )}
        {entity.lifecycle_states && entity.lifecycle_states.length > 0 && (
          <div>
            <div className="text-[9px] uppercase font-bold text-[#747480] flex items-center gap-1 mb-0.5">
              <Tag className="w-3 h-3" /> Lifecycle states
            </div>
            <div className="flex flex-wrap gap-1">
              {entity.lifecycle_states.map((s, i) => (
                <span key={i} className="text-[10px] bg-[#FFFCE6] border border-[#FFE600] px-1.5 py-0.5 rounded-sm font-mono">
                  {s}
                </span>
              ))}
            </div>
          </div>
        )}
        {entity.backed_by_tables && entity.backed_by_tables.length > 0 && (
          <ListSection icon={Database} label={`Backed by tables (${entity.backed_by_tables.length})`}
            items={entity.backed_by_tables} />
        )}
        {entity.implemented_in_classes && entity.implemented_in_classes.length > 0 && (
          <ListSection icon={FileCode} label={`Implemented in classes (${entity.implemented_in_classes.length})`}
            items={entity.implemented_in_classes} />
        )}
      </div>

      {rels.length > 0 && (
        <div className="mt-4">
          <div className="text-[10px] uppercase font-bold text-[#747480] mb-1">
            Relationships ({rels.length})
          </div>
          <div className="space-y-0.5">
            {rels.map((r, i) => {
              const isOut = r.source === entity.id;
              const otherId = isOut ? r.target : r.source;
              const other = byId[otherId];
              if (!other) return null;
              const otherMeta = palette[other.domain] || DOMAIN_PALETTE[0];
              return (
                <button key={i} onClick={() => onSelect(other)}
                  className="w-full flex items-center gap-2 text-[10px] px-2 py-1 rounded-sm hover:bg-[#F6F6FA] text-left">
                  <span className="text-[9px] font-mono text-[#747480] w-4">{isOut ? "→" : "←"}</span>
                  <span className="text-[#2E2E38] font-semibold uppercase text-[9px] tracking-wide">
                    {r.verb || "relates to"}
                  </span>
                  <span className="font-semibold truncate" style={{ color: otherMeta.color }}>
                    {other.name}
                  </span>
                  {r.kind === "fk" && (
                    <span className="text-[8px] text-[#9CA3AF] uppercase ml-auto">fk</span>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function DetailRow({ icon: Icon, label, value }) {
  return (
    <div>
      <div className="text-[9px] uppercase font-bold text-[#747480] flex items-center gap-1 mb-0.5">
        <Icon className="w-3 h-3" /> {label}
      </div>
      <div className="text-[11px] text-[#2E2E38]">{value}</div>
    </div>
  );
}

function ListSection({ icon: Icon, label, items }) {
  return (
    <div>
      <div className="text-[9px] uppercase font-bold text-[#747480] flex items-center gap-1 mb-0.5">
        <Icon className="w-3 h-3" /> {label}
      </div>
      <div className="flex flex-wrap gap-1">
        {items.slice(0, 30).map((s, i) => (
          <span key={i} className="text-[10px] bg-[#F6F6FA] border border-[#E6E6E6] px-1.5 py-0.5 rounded-sm font-mono break-all">
            {s}
          </span>
        ))}
        {items.length > 30 && (
          <span className="text-[10px] text-[#747480]">+{items.length - 30} more</span>
        )}
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────
// Main page
// ────────────────────────────────────────────────────────────────────
export default function OntologyStudioPage() {
  const { active } = useProjects();
  const projectId = active?.id;
  const [mode, setMode] = useState("graph");
  const [data, setData] = useState(null);
  const [search, setSearch] = useState("");
  const [activeDomains, setActiveDomains] = useState(new Set());
  const [selectedId, setSelectedId] = useState(null);

  const [jobStatus, setJobStatus] = useState("idle"); // idle | queued | running | done | error
  const [jobError, setJobError] = useState("");
  const [progress, setProgress] = useState(0);
  const pollRef = useRef(null);

  // Try to load cached ontology on mount
  const loadCached = useCallback(async () => {
    if (!projectId) return;
    try {
      const r = await getBusinessOntology(projectId);
      applyResult(r);
    } catch {
      // 404 — no cache yet, leave empty
      setData(null);
    }
  }, [projectId]);

  const applyResult = useCallback((r) => {
    setData(r);
    setActiveDomains(new Set(r.domains || []));
    setSelectedId(null);
  }, []);

  useEffect(() => { loadCached(); }, [loadCached]);

  // Job polling for generation / regeneration
  const startJob = useCallback(async (force = false) => {
    if (!projectId) return;
    setJobStatus("queued");
    setJobError("");
    setProgress(0.05);
    try {
      const start = await startBusinessOntologyJob(projectId, force);
      if (start.status === "done" && start.cached) {
        // Server returned cached immediately
        await loadCached();
        setJobStatus("done");
        setProgress(1);
        return;
      }
      const jobId = start.job_id;
      // Poll every 2s
      pollRef.current = setInterval(async () => {
        try {
          const j = await getBusinessOntologyJob(projectId, jobId);
          setJobStatus(j.status);
          setProgress((p) => Math.min(0.95, Math.max(p, j.progress || p + 0.05)));
          if (j.status === "done") {
            clearInterval(pollRef.current); pollRef.current = null;
            setProgress(1);
            if (j.result) applyResult(j.result);
            else await loadCached();
            toast.success(force ? "Business ontology regenerated." : "Business ontology built.");
          } else if (j.status === "error") {
            clearInterval(pollRef.current); pollRef.current = null;
            setJobError(j.error || "Generation failed.");
            toast.error("Generation failed: " + (j.error || "unknown"));
          }
        } catch (e) {
          clearInterval(pollRef.current); pollRef.current = null;
          setJobStatus("error");
          setJobError(e?.response?.data?.detail || e.message);
        }
      }, 2000);
    } catch (e) {
      setJobStatus("error");
      setJobError(e?.response?.data?.detail || e.message);
      toast.error("Failed to start job: " + (e?.response?.data?.detail || e.message));
    }
  }, [projectId, applyResult, loadCached]);

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  const palette = useMemo(() => paletteForDomains(data?.domains || []), [data]);
  const byId = useMemo(
    () => Object.fromEntries((data?.entities || []).map((e) => [e.id, e])),
    [data]
  );
  const selected = selectedId ? byId[selectedId] : null;

  const exportJson = () => {
    if (!data) return;
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `business_ontology_${projectId}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const toggleDomain = (d) => {
    setActiveDomains((prev) => {
      const next = new Set(prev);
      if (next.has(d)) next.delete(d); else next.add(d);
      return next;
    });
  };

  if (!projectId) {
    return <div className="p-8 text-[#747480]" data-testid="ontology-no-project">No active project selected.</div>;
  }

  const running = jobStatus === "queued" || jobStatus === "running";

  return (
    <div className="flex-1 flex flex-col min-w-0 bg-[#F6F6FA]" data-testid="ontology-studio-page">
      {/* Header */}
      <header className="bg-white border-b-2 border-[#FFE600] px-6 py-3 flex items-center justify-between">
        <div>
          <Link to="/discovery" data-testid="back-to-discovery" className="text-[10px] uppercase tracking-widest text-[#747480] flex items-center gap-1 hover:text-[#2E2E38]">
            <ArrowLeft className="w-3 h-3" /> Back to Discovery
          </Link>
          <h1 className="font-display text-lg font-bold tracking-tight text-[#2E2E38] flex items-center gap-2">
            <Boxes className="w-4 h-4 text-[#FFE600]" /> Ontology Studio · Business Domain
          </h1>
        </div>
        <div className="flex items-center gap-2">
          {data && (
            <span className="text-[11px] text-[#747480]" data-testid="ontology-overall-stats">
              {data.stats?.total_entities || 0} entities · {data.stats?.total_relationships || 0} relationships · {data.stats?.total_domains || 0} domains
            </span>
          )}
          <div className="flex border border-[#E6E6E6] rounded-sm overflow-hidden">
            <button onClick={() => setMode("graph")} data-testid="mode-graph"
              className={`text-[11px] px-2 py-1 ${mode === "graph" ? "bg-[#FFE600] text-[#2E2E38] font-bold" : "bg-white text-[#747480]"}`}>
              <Network className="w-3 h-3 inline mr-1" /> Graph
            </button>
            <button onClick={() => setMode("tree")} data-testid="mode-tree"
              className={`text-[11px] px-2 py-1 ${mode === "tree" ? "bg-[#FFE600] text-[#2E2E38] font-bold" : "bg-white text-[#747480]"}`}>
              <ListTree className="w-3 h-3 inline mr-1" /> Tree
            </button>
          </div>
          <Button onClick={() => startJob(true)} disabled={running}
            variant="outline" className="h-7 text-[11px]" data-testid="regenerate-btn">
            {running ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <RefreshCw className="w-3 h-3 mr-1" />}
            {data ? "Regenerate" : "Build now"}
          </Button>
          <Button onClick={exportJson} disabled={!data}
            variant="outline" className="h-7 text-[11px]" data-testid="export-ontology">
            <Download className="w-3 h-3 mr-1" /> Export JSON
          </Button>
        </div>
      </header>

      {/* Stale banner */}
      {data?.stale && (
        <div className="bg-amber-50 border-b border-amber-200 px-6 py-2 text-[11px] text-amber-800 flex items-center gap-2" data-testid="stale-banner">
          <AlertTriangle className="w-3 h-3" />
          <span>Your KB has changed since this ontology was generated. Click <strong>Regenerate</strong> to refresh.</span>
        </div>
      )}

      {/* Filter strip */}
      {data && (
        <div className="bg-white border-b border-[#E6E6E6] px-6 py-2 flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-1">
            <Search className="w-3 h-3 text-[#747480]" />
            <input value={search} onChange={(e) => setSearch(e.target.value)}
              placeholder="Search entities…"
              data-testid="ontology-search"
              className="text-[11px] border border-[#E6E6E6] focus:border-[#2E2E38] outline-none rounded-sm px-2 py-1 w-44" />
          </div>
          <div className="flex items-center gap-1 flex-wrap">
            <Filter className="w-3 h-3 text-[#747480]" />
            {(data.domains || []).map((d) => {
              const meta = palette[d] || DOMAIN_PALETTE[0];
              const on = activeDomains.has(d);
              const count = (data.entities || []).filter((e) => e.domain === d).length;
              return (
                <button key={d} onClick={() => toggleDomain(d)}
                  data-testid={`filter-${d}`}
                  className={`text-[10px] px-1.5 py-0.5 rounded-sm border ${on ? "" : "opacity-40"}`}
                  style={{ background: meta.bg, color: meta.color, borderColor: meta.border }}>
                  {d} <span className="opacity-70">·{count}</span>
                </button>
              );
            })}
          </div>
          {data.source === "deterministic" && (
            <span className="ml-auto text-[10px] text-amber-700">
              ⚠ LLM enrichment was skipped — showing deterministic clusters only.
            </span>
          )}
        </div>
      )}

      {/* Body */}
      <div className="flex-1 min-h-0 grid grid-cols-12 overflow-hidden">
        {!data ? (
          <div className="col-span-12 flex items-center justify-center text-center p-8" data-testid="ontology-empty">
            {running ? (
              <div>
                <Loader2 className="w-8 h-8 text-[#FFE600] animate-spin mx-auto mb-3" />
                <div className="font-display text-sm font-bold text-[#2E2E38]">Building business ontology…</div>
                <div className="text-[11px] text-[#747480] mt-1">
                  Clustering by domain, then asking the LLM to rename + enrich entities. Usually 30–90s.
                </div>
                <div className="w-64 h-1 bg-[#E6E6E6] rounded-sm mt-3 mx-auto overflow-hidden">
                  <div className="h-full bg-[#FFE600] transition-all" style={{ width: `${Math.round(progress * 100)}%` }} />
                </div>
              </div>
            ) : jobStatus === "error" ? (
              <div>
                <AlertTriangle className="w-8 h-8 text-rose-500 mx-auto mb-3" />
                <div className="font-display text-sm font-bold text-[#2E2E38]">Generation failed</div>
                <div className="text-[11px] text-rose-700 mt-1 max-w-md">{jobError}</div>
                <Button onClick={() => startJob(true)} className="mt-3 h-7 text-[11px] bg-[#FFE600] text-[#2E2E38] hover:bg-[#FFD500]" data-testid="retry-btn">
                  Retry
                </Button>
              </div>
            ) : (
              <div>
                <Boxes className="w-10 h-10 text-[#FFE600] mx-auto mb-3" />
                <div className="font-display text-sm font-bold text-[#2E2E38]">No business ontology yet</div>
                <div className="text-[11px] text-[#747480] mt-1 max-w-md">
                  Click <strong>Build now</strong> to derive business-domain entities from your KB
                  (deterministic clustering + LLM enrichment).
                </div>
                <Button onClick={() => startJob(false)} className="mt-3 h-8 text-[11px] bg-[#FFE600] text-[#2E2E38] hover:bg-[#FFD500]" data-testid="build-now-btn">
                  <RefreshCw className="w-3 h-3 mr-1" /> Build now
                </Button>
              </div>
            )}
          </div>
        ) : (
          <>
            <div className="col-span-3 min-w-0 overflow-hidden border-r border-[#E6E6E6]">
              <TreeView
                entities={data.entities || []}
                search={search} activeDomains={activeDomains} palette={palette}
                selected={selectedId} onSelect={(e) => setSelectedId(e.id)}
              />
            </div>
            <div className="col-span-6 min-w-0 overflow-hidden">
              {mode === "graph" ? (
                <GraphView
                  entities={data.entities || []} relationships={data.relationships || []}
                  search={search} activeDomains={activeDomains} palette={palette}
                  selected={selectedId} onSelect={(e) => setSelectedId(e.id)}
                />
              ) : (
                <TreeView
                  entities={data.entities || []}
                  search={search} activeDomains={activeDomains} palette={palette}
                  selected={selectedId} onSelect={(e) => setSelectedId(e.id)}
                />
              )}
            </div>
            <div className="col-span-3 min-w-0 overflow-hidden border-l border-[#E6E6E6]">
              <DetailPanel entity={selected} relationships={data.relationships || []}
                byId={byId} palette={palette} onSelect={(e) => setSelectedId(e.id)} />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
