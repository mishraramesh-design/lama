import React, { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  ArrowLeft, Loader2, Network, ListTree, Search, Download,
  ZoomIn, ZoomOut, Maximize2, RotateCcw, Filter, Boxes,
  GitCompare, Camera, Trash2, X,
} from "lucide-react";
import { toast } from "sonner";
import { useProjects } from "@/state/ProjectContext";
import {
  getOntology, createOntologySnapshot, listOntologySnapshots,
  deleteOntologySnapshot, diffOntology,
} from "@/lib/api";
import { Button } from "@/components/ui/button";

// ────────────────────────────────────────────────────────────────────
// Type metadata — colours + icons
// ────────────────────────────────────────────────────────────────────
const TYPE_META = {
  Class:        { color: "#2E2E38", bg: "#F6F6FA", border: "#2E2E38" },
  Interface:    { color: "#7C3AED", bg: "#F3EFFF", border: "#7C3AED" },
  Method:       { color: "#0EA5E9", bg: "#E0F2FE", border: "#0284C7" },
  Table:        { color: "#FFE600", bg: "#FFFCE6", border: "#CCB800" },
  Column:       { color: "#6B7280", bg: "#F3F4F6", border: "#9CA3AF" },
  Route:        { color: "#10B981", bg: "#D1FAE5", border: "#059669" },
  JspForm:      { color: "#F59E0B", bg: "#FEF3C7", border: "#B45309" },
  JspInclude:   { color: "#EC4899", bg: "#FCE7F3", border: "#BE185D" },
  Role:         { color: "#EF4444", bg: "#FEE2E2", border: "#B91C1C" },
};

const EDGE_KIND_COLORS = {
  extends:      "#7C3AED",
  implements:   "#A855F7",
  has_method:   "#0EA5E9",
  uses_table:   "#FFB800",
  has_column:   "#9CA3AF",
  references:   "#10B981",
  posts_to:     "#F59E0B",
};

// ────────────────────────────────────────────────────────────────────
// Force-directed layout (Fruchterman-Reingold, ~30 iterations)
// ────────────────────────────────────────────────────────────────────
function forceLayout(nodes, edges, { width = 1400, height = 900, iter = 60 } = {}) {
  if (!nodes.length) return [];
  const k = Math.sqrt((width * height) / nodes.length) * 0.7;
  const positioned = nodes.map((n, i) => ({
    ...n,
    x: width / 2 + (Math.random() - 0.5) * width * 0.6,
    y: height / 2 + (Math.random() - 0.5) * height * 0.6,
    dx: 0, dy: 0,
  }));
  const byId = Object.fromEntries(positioned.map((n) => [n.id, n]));
  let t = width / 12;
  for (let step = 0; step < iter; step++) {
    // Repulsion
    for (const a of positioned) { a.dx = 0; a.dy = 0; }
    for (let i = 0; i < positioned.length; i++) {
      for (let j = i + 1; j < positioned.length; j++) {
        const a = positioned[i], b = positioned[j];
        const dx = a.x - b.x, dy = a.y - b.y;
        const d = Math.sqrt(dx * dx + dy * dy) || 0.01;
        const f = (k * k) / d;
        const fx = (dx / d) * f, fy = (dy / d) * f;
        a.dx += fx; a.dy += fy;
        b.dx -= fx; b.dy -= fy;
      }
    }
    // Attraction along edges
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
    // Apply with cooling
    for (const a of positioned) {
      const disp = Math.sqrt(a.dx * a.dx + a.dy * a.dy) || 0.01;
      a.x += (a.dx / disp) * Math.min(disp, t);
      a.y += (a.dy / disp) * Math.min(disp, t);
      a.x = Math.max(40, Math.min(width - 40, a.x));
      a.y = Math.max(40, Math.min(height - 40, a.y));
    }
    t = Math.max(t * 0.92, 1);
  }
  return positioned;
}

// ────────────────────────────────────────────────────────────────────
// Graph view (SVG with pan + zoom)
// ────────────────────────────────────────────────────────────────────
function GraphView({ nodes, edges, selectedTypes, search, onSelect, selected }) {
  const svgRef = useRef(null);
  const [view, setView] = useState({ scale: 1, tx: 0, ty: 0 });
  const dragRef = useRef(null);

  const filteredNodes = useMemo(() => nodes.filter((n) =>
    selectedTypes.has(n.type) &&
    (!search || (n.label || "").toLowerCase().includes(search.toLowerCase()))
  ), [nodes, selectedTypes, search]);
  const visibleIds = useMemo(() => new Set(filteredNodes.map((n) => n.id)), [filteredNodes]);
  const filteredEdges = useMemo(() => edges.filter((e) =>
    visibleIds.has(e.source) && visibleIds.has(e.target)
  ), [edges, visibleIds]);

  const positioned = useMemo(
    () => forceLayout(filteredNodes, filteredEdges, { width: 1600, height: 1100 }),
    [filteredNodes, filteredEdges]
  );
  const byId = useMemo(() => Object.fromEntries(positioned.map((n) => [n.id, n])), [positioned]);

  const onWheel = useCallback((e) => {
    e.preventDefault();
    const dir = e.deltaY < 0 ? 1.1 : 1 / 1.1;
    setView((v) => ({ ...v, scale: Math.max(0.2, Math.min(4, v.scale * dir)) }));
  }, []);

  const onMouseDown = (e) => {
    if (e.target.dataset && e.target.dataset.node) return; // node click handled elsewhere
    dragRef.current = { x: e.clientX, y: e.clientY, tx: view.tx, ty: view.ty };
  };
  const onMouseMove = (e) => {
    if (!dragRef.current) return;
    setView((v) => ({ ...v,
      tx: dragRef.current.tx + (e.clientX - dragRef.current.x),
      ty: dragRef.current.ty + (e.clientY - dragRef.current.y),
    }));
  };
  const onMouseUp = () => { dragRef.current = null; };

  // Highlight: when something is selected, dim everything else
  const isHighlighted = (nid) => {
    if (!selected) return true;
    if (nid === selected) return true;
    return filteredEdges.some((e) =>
      (e.source === selected && e.target === nid) ||
      (e.target === selected && e.source === nid)
    );
  };

  return (
    <div className="relative w-full h-full overflow-hidden bg-[#FAFAFC]" data-testid="ontology-graph">
      {/* Zoom controls */}
      <div className="absolute top-3 right-3 z-10 flex flex-col gap-1 bg-white border border-[#E6E6E6] rounded-sm shadow-sm">
        <button onClick={() => setView((v) => ({ ...v, scale: Math.min(4, v.scale * 1.2) }))} className="p-1.5 hover:bg-[#F6F6FA]"><ZoomIn className="w-3 h-3" /></button>
        <button onClick={() => setView((v) => ({ ...v, scale: Math.max(0.2, v.scale / 1.2) }))} className="p-1.5 hover:bg-[#F6F6FA]"><ZoomOut className="w-3 h-3" /></button>
        <button onClick={() => setView({ scale: 1, tx: 0, ty: 0 })} title="Reset view" className="p-1.5 hover:bg-[#F6F6FA]"><RotateCcw className="w-3 h-3" /></button>
      </div>
      <div className="absolute bottom-3 left-3 z-10 bg-white border border-[#E6E6E6] rounded-sm px-2 py-1 text-[10px] text-[#747480]" data-testid="graph-stats">
        {positioned.length} nodes · {filteredEdges.length} edges · zoom {Math.round(view.scale * 100)}%
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
          {Object.entries(EDGE_KIND_COLORS).map(([k, c]) => (
            <marker key={k} id={`arrow-${k}`} viewBox="0 -5 10 10" refX="14" refY="0" markerWidth="6" markerHeight="6" orient="auto">
              <path d="M0,-5L10,0L0,5" fill={c} />
            </marker>
          ))}
        </defs>
        <g transform={`translate(${view.tx} ${view.ty}) scale(${view.scale})`}>
          {/* Edges */}
          {filteredEdges.map((e, i) => {
            const a = byId[e.source], b = byId[e.target];
            if (!a || !b) return null;
            const color = EDGE_KIND_COLORS[e.kind] || "#9CA3AF";
            const dim = selected && !(a.id === selected || b.id === selected);
            return (
              <line
                key={`e${i}`}
                x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                stroke={color} strokeWidth={dim ? 0.5 : 1.2}
                opacity={dim ? 0.15 : 0.7}
                markerEnd={`url(#arrow-${e.kind})`}
              />
            );
          })}
          {/* Nodes */}
          {positioned.map((n) => {
            const meta = TYPE_META[n.type] || { color: "#444", bg: "#fff", border: "#888" };
            const r = n.type === "Method" || n.type === "Column" ? 6 : n.type === "Table" || n.type === "Class" ? 11 : 9;
            const hl = isHighlighted(n.id);
            return (
              <g
                key={n.id}
                data-node={n.id}
                onClick={(e) => { e.stopPropagation(); onSelect(n); }}
                style={{ cursor: "pointer" }}
                opacity={hl ? 1 : 0.2}
              >
                <circle cx={n.x} cy={n.y} r={r}
                  fill={meta.bg} stroke={meta.border} strokeWidth={n.id === selected ? 3 : 1.3} />
                <text x={n.x + r + 3} y={n.y + 3} fontSize={10} fill={meta.color}>
                  {(n.label || "").length > 24 ? (n.label || "").slice(0, 24) + "…" : n.label}
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
// Tree view (grouped by type)
// ────────────────────────────────────────────────────────────────────
function TreeView({ nodes, edges, selectedTypes, search, onSelect, selected }) {
  const grouped = useMemo(() => {
    const out = {};
    for (const n of nodes) {
      if (!selectedTypes.has(n.type)) continue;
      if (search && !(n.label || "").toLowerCase().includes(search.toLowerCase())) continue;
      out[n.type] = out[n.type] || [];
      out[n.type].push(n);
    }
    Object.values(out).forEach((arr) => arr.sort((a, b) => (a.label || "").localeCompare(b.label || "")));
    return out;
  }, [nodes, selectedTypes, search]);

  return (
    <div className="overflow-y-auto h-full p-3 bg-white border-r border-[#E6E6E6]" data-testid="ontology-tree">
      {Object.entries(grouped).map(([type, list]) => {
        const meta = TYPE_META[type] || {};
        return (
          <div key={type} className="mb-3">
            <div className="text-[10px] uppercase font-bold mb-1" style={{ color: meta.color }}>
              {type} <span className="text-[#747480]">({list.length})</span>
            </div>
            <div className="space-y-0.5">
              {list.map((n) => (
                <button
                  key={n.id}
                  onClick={() => onSelect(n)}
                  data-testid={`tree-${n.id}`}
                  className={`w-full text-left text-[11px] px-2 py-1 rounded-sm font-mono truncate ${
                    selected === n.id ? "bg-[#FFFCE6] border border-[#FFE600]" : "hover:bg-[#F6F6FA]"
                  }`}
                  style={{ borderLeft: `3px solid ${meta.border || "#ccc"}` }}
                >
                  {n.label}
                </button>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────
// Selected-node detail panel
// ────────────────────────────────────────────────────────────────────
function DetailPanel({ node, neighbours, onSelect }) {
  if (!node) {
    return (
      <div className="p-4 text-[11px] text-[#747480] flex items-center justify-center h-full">
        <div className="text-center">
          <Network className="w-6 h-6 mx-auto mb-2 text-[#FFE600]" />
          Click any node to see its details, FK references, and downstream methods.
        </div>
      </div>
    );
  }
  const meta = TYPE_META[node.type] || {};
  return (
    <div className="p-3 overflow-y-auto h-full bg-white" data-testid={`detail-${node.id}`}>
      <div className="text-[9px] uppercase font-bold mb-1" style={{ color: meta.color }}>{node.type}</div>
      <div className="font-display font-bold text-[#2E2E38] break-all">{node.label}</div>
      <div className="text-[10px] font-mono text-[#747480] break-all mt-0.5">{node.id}</div>

      <dl className="mt-3 text-[11px] space-y-1">
        {node.namespace && <Row label="Namespace" value={node.namespace} />}
        {node.source && <Row label="Source" value={node.source} mono />}
        {node.extends && <Row label="Extends" value={node.extends} mono />}
        {node.implements?.length > 0 && <Row label="Implements" value={node.implements.join(", ")} mono />}
        {node.is_jpa_entity && <Row label="JPA Entity" value="Yes" />}
        {node.verb && <Row label="HTTP" value={node.verb} />}
        {node.handler && <Row label="Handler" value={node.handler} mono />}
        {node.data_type && <Row label="Type" value={node.data_type} mono />}
        {node.is_pk && <Row label="PK" value="Yes" />}
        {node.is_fk && <Row label="FK" value="Yes" />}
        {node.via && <Row label="Detected via" value={node.via} />}
        {node.params && <Row label="Params" value={node.params} mono />}
        {node.tables?.length > 0 && <Row label="Reads/Writes" value={node.tables.join(", ")} mono />}
      </dl>

      {neighbours.length > 0 && (
        <div className="mt-4">
          <div className="text-[10px] uppercase font-bold text-[#747480] mb-1">
            Connected ({neighbours.length})
          </div>
          <div className="space-y-0.5">
            {neighbours.map((edge, i) => (
              <button
                key={i}
                onClick={() => onSelect(edge.other)}
                className="w-full flex items-center gap-2 text-[10px] px-2 py-1 rounded-sm hover:bg-[#F6F6FA] text-left"
              >
                <span className="text-[#747480] uppercase text-[8px] font-bold">{edge.kind}</span>
                <span
                  className="font-mono truncate"
                  style={{ color: (TYPE_META[edge.other.type] || {}).color }}
                >
                  {edge.other.label}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
function Row({ label, value, mono }) {
  return (
    <div>
      <dt className="text-[9px] uppercase font-bold text-[#747480]">{label}</dt>
      <dd className={`${mono ? "font-mono" : ""} text-[#2E2E38] break-all`}>{value}</dd>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────
// Main page
// ────────────────────────────────────────────────────────────────────
export default function OntologyStudioPage() {
  const { active } = useProjects();
  const projectId = active?.id;
  const [params] = useSearchParams();
  const [mode, setMode] = useState(params.get("mode") || "graph");
  const [data, setData] = useState({ nodes: [], edges: [], stats: {} });
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState(null);
  const [selectedTypes, setSelectedTypes] = useState(new Set(Object.keys(TYPE_META)));
  const [search, setSearch] = useState("");

  // Snapshots & diff
  const [snapshots, setSnapshots] = useState([]);
  const [diffOpen, setDiffOpen] = useState(false);
  const [diffA, setDiffA] = useState("");
  const [diffB, setDiffB] = useState("current");
  const [diffResult, setDiffResult] = useState(null);
  const [diffLoading, setDiffLoading] = useState(false);

  const refreshSnapshots = useCallback(async () => {
    if (!projectId) return;
    try { const r = await listOntologySnapshots(projectId); setSnapshots(r.snapshots || []); } catch { /* */ }
  }, [projectId]);
  useEffect(() => { refreshSnapshots(); }, [refreshSnapshots]);

  const onSnapshot = async () => {
    if (!projectId) return;
    const name = window.prompt("Snapshot name?", `snapshot-${new Date().toISOString().slice(0, 19).replace(/[T:]/g, "-")}`);
    if (!name) return;
    try {
      const r = await createOntologySnapshot(projectId, name);
      toast.success(`Saved snapshot "${r.name}" (${r.stats.total_nodes} nodes)`);
      await refreshSnapshots();
    } catch (e) { toast.error("Snapshot failed: " + (e?.response?.data?.detail || e.message)); }
  };

  const onDeleteSnapshot = async (id) => {
    if (!window.confirm("Delete this snapshot?")) return;
    try { await deleteOntologySnapshot(projectId, id); toast.success("Deleted"); refreshSnapshots(); }
    catch { toast.error("Delete failed"); }
  };

  const onRunDiff = async () => {
    if (!diffA) { toast.error("Pick a snapshot for side A first."); return; }
    setDiffLoading(true);
    try { const r = await diffOntology(projectId, diffA, diffB); setDiffResult(r); }
    catch (e) { toast.error("Diff failed: " + (e?.response?.data?.detail || e.message)); }
    finally { setDiffLoading(false); }
  };

  const refresh = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const r = await getOntology(projectId);
      setData(r);
    } catch (e) {
      toast.error("Failed to load ontology: " + (e?.response?.data?.detail || e.message));
    } finally { setLoading(false); }
  }, [projectId]);
  useEffect(() => { refresh(); }, [refresh]);

  const selectedNode = useMemo(
    () => data.nodes.find((n) => n.id === selectedId) || null,
    [data.nodes, selectedId]
  );
  const neighbours = useMemo(() => {
    if (!selectedNode) return [];
    const byId = Object.fromEntries(data.nodes.map((n) => [n.id, n]));
    const out = [];
    for (const e of data.edges) {
      if (e.source === selectedNode.id && byId[e.target]) out.push({ kind: e.kind, other: byId[e.target] });
      else if (e.target === selectedNode.id && byId[e.source]) out.push({ kind: e.kind, other: byId[e.source] });
    }
    return out;
  }, [data, selectedNode]);

  const toggleType = (t) => {
    const next = new Set(selectedTypes);
    if (next.has(t)) next.delete(t); else next.add(t);
    setSelectedTypes(next);
  };

  const exportJson = () => {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `ontology_${projectId || "project"}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  if (!projectId) {
    return <div className="p-8 text-[#747480]">No active project selected.</div>;
  }

  return (
    <div className="flex-1 flex flex-col min-w-0 bg-[#F6F6FA]" data-testid="ontology-studio-page">
      <header className="bg-white border-b-2 border-[#FFE600] px-6 py-3 flex items-center justify-between">
        <div>
          <Link to="/discovery" data-testid="back-to-discovery" className="text-[10px] uppercase tracking-widest text-[#747480] flex items-center gap-1 hover:text-[#2E2E38]">
            <ArrowLeft className="w-3 h-3" /> Back to Discovery
          </Link>
          <h1 className="font-display text-lg font-bold tracking-tight text-[#2E2E38] flex items-center gap-2">
            <Boxes className="w-4 h-4 text-[#FFE600]" /> Ontology Studio
          </h1>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-[#747480]">
            {data.stats.total_nodes || 0} nodes · {data.stats.total_edges || 0} edges
          </span>
          <div className="flex border border-[#E6E6E6] rounded-sm overflow-hidden">
            <button onClick={() => setMode("graph")} data-testid="mode-graph" className={`text-[11px] px-2 py-1 ${mode === "graph" ? "bg-[#FFE600] text-[#2E2E38] font-bold" : "bg-white text-[#747480]"}`}>
              <Network className="w-3 h-3 inline mr-1" /> Graph
            </button>
            <button onClick={() => setMode("tree")} data-testid="mode-tree" className={`text-[11px] px-2 py-1 ${mode === "tree" ? "bg-[#FFE600] text-[#2E2E38] font-bold" : "bg-white text-[#747480]"}`}>
              <ListTree className="w-3 h-3 inline mr-1" /> Tree
            </button>
          </div>
          <Button onClick={onSnapshot} variant="outline" className="h-7 text-[11px]" data-testid="snapshot-btn">
            <Camera className="w-3 h-3 mr-1" /> Snapshot
          </Button>
          <Button onClick={() => setDiffOpen(true)} variant="outline" className="h-7 text-[11px]" data-testid="open-diff-btn">
            <GitCompare className="w-3 h-3 mr-1" /> Diff
            {snapshots.length > 0 && <span className="ml-1 text-[9px] bg-[#FFE600] text-[#2E2E38] font-bold px-1 rounded-sm">{snapshots.length}</span>}
          </Button>
          <Button onClick={exportJson} variant="outline" className="h-7 text-[11px]" data-testid="export-ontology">
            <Download className="w-3 h-3 mr-1" /> Export JSON
          </Button>
        </div>
      </header>

      {/* Filter strip */}
      <div className="bg-white border-b border-[#E6E6E6] px-6 py-2 flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-1">
          <Search className="w-3 h-3 text-[#747480]" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search nodes…"
            data-testid="ontology-search"
            className="text-[11px] border border-[#E6E6E6] focus:border-[#2E2E38] outline-none rounded-sm px-2 py-1 w-44"
          />
        </div>
        <div className="flex items-center gap-1 flex-wrap">
          <Filter className="w-3 h-3 text-[#747480]" />
          {Object.entries(TYPE_META).map(([t, meta]) => {
            const count = data.stats.by_type?.[t] || 0;
            const on = selectedTypes.has(t);
            return (
              <button
                key={t}
                onClick={() => toggleType(t)}
                data-testid={`filter-${t}`}
                className={`text-[10px] px-1.5 py-0.5 rounded-sm border ${on ? "" : "opacity-40"}`}
                style={{ background: meta.bg, color: meta.color, borderColor: meta.border }}
              >
                {t} {count > 0 && <span className="opacity-70">·{count}</span>}
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex-1 min-h-0 grid grid-cols-12 overflow-hidden">
        {/* Left: tree or compact graph */}
        <div className="col-span-3 min-w-0 overflow-hidden border-r border-[#E6E6E6]">
          <TreeView
            nodes={data.nodes} edges={data.edges}
            selectedTypes={selectedTypes} search={search}
            selected={selectedId} onSelect={(n) => setSelectedId(n.id)}
          />
        </div>
        {/* Center: graph or full tree */}
        <div className="col-span-6 min-w-0 overflow-hidden">
          {loading ? (
            <div className="h-full flex items-center justify-center text-[#747480]">
              <Loader2 className="w-4 h-4 animate-spin mr-2" /> Loading ontology…
            </div>
          ) : mode === "graph" ? (
            <GraphView
              nodes={data.nodes} edges={data.edges}
              selectedTypes={selectedTypes} search={search}
              selected={selectedId} onSelect={(n) => setSelectedId(n.id)}
            />
          ) : (
            <TreeView
              nodes={data.nodes} edges={data.edges}
              selectedTypes={selectedTypes} search={search}
              selected={selectedId} onSelect={(n) => setSelectedId(n.id)}
            />
          )}
        </div>
        {/* Right: details */}
        <div className="col-span-3 min-w-0 overflow-hidden border-l border-[#E6E6E6]">
          <DetailPanel node={selectedNode} neighbours={neighbours} onSelect={(n) => setSelectedId(n.id)} />
        </div>
      </div>

      {/* Diff modal */}
      {diffOpen && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" data-testid="diff-modal">
          <div className="bg-white border-2 border-[#FFE600] rounded-sm w-full max-w-5xl h-[88vh] flex flex-col">
            <div className="px-4 py-3 border-b border-[#E6E6E6] flex items-center justify-between">
              <div>
                <div className="text-[10px] uppercase tracking-widest text-[#747480]">Ontology Diff</div>
                <div className="text-sm font-display font-bold">Compare two snapshots (or any snapshot vs current)</div>
              </div>
              <button onClick={() => { setDiffOpen(false); setDiffResult(null); }} data-testid="diff-close" className="text-[#747480] hover:text-[#2E2E38]"><X className="w-4 h-4" /></button>
            </div>
            <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-3 border-b border-[#E6E6E6]">
              {/* Side A */}
              <div>
                <div className="text-[10px] uppercase font-bold text-[#747480] mb-1">Side A</div>
                <select value={diffA} onChange={(e) => setDiffA(e.target.value)} data-testid="diff-select-a" className="w-full text-[11px] border border-[#E6E6E6] rounded-sm px-2 py-1.5">
                  <option value="">— pick a snapshot —</option>
                  {snapshots.map((s) => (
                    <option key={s.id} value={s.id}>{s.name} · {(s.stats || {}).total_nodes || 0} nodes · {(s.created_at || "").slice(0, 19).replace("T", " ")}</option>
                  ))}
                </select>
              </div>
              {/* Side B */}
              <div>
                <div className="text-[10px] uppercase font-bold text-[#747480] mb-1">Side B</div>
                <select value={diffB} onChange={(e) => setDiffB(e.target.value)} data-testid="diff-select-b" className="w-full text-[11px] border border-[#E6E6E6] rounded-sm px-2 py-1.5">
                  <option value="current">Current ontology</option>
                  {snapshots.map((s) => (
                    <option key={s.id} value={s.id}>{s.name} · {(s.stats || {}).total_nodes || 0} nodes</option>
                  ))}
                </select>
              </div>
              {snapshots.length === 0 && (
                <div className="md:col-span-2 text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded-sm p-2">
                  No snapshots yet. Click <strong>Snapshot</strong> in the header to capture the current ontology, then re-upload files or re-build the KB, and come back here to diff.
                </div>
              )}
              <div className="md:col-span-2 flex items-center gap-2">
                <Button onClick={onRunDiff} disabled={!diffA || diffLoading} data-testid="diff-run" className="h-8 text-[11px] bg-[#FFE600] text-[#2E2E38] hover:bg-[#FFD500]">
                  {diffLoading ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <GitCompare className="w-3 h-3 mr-1" />} Compare
                </Button>
                {snapshots.length > 0 && (
                  <details className="text-[10px] ml-auto">
                    <summary className="cursor-pointer text-[#747480]">Manage snapshots ({snapshots.length})</summary>
                    <div className="mt-1 space-y-0.5 max-h-32 overflow-y-auto">
                      {snapshots.map((s) => (
                        <div key={s.id} className="flex items-center gap-2 text-[10px]">
                          <span className="font-mono truncate flex-1">{s.name}</span>
                          <button onClick={() => onDeleteSnapshot(s.id)} className="text-rose-500 hover:bg-rose-50 rounded-sm p-0.5"><Trash2 className="w-3 h-3" /></button>
                        </div>
                      ))}
                    </div>
                  </details>
                )}
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-4" data-testid="diff-result">
              {!diffResult && <div className="text-[11px] text-[#747480] text-center mt-12">Pick two sides and click Compare.</div>}
              {diffResult && (
                <div className="space-y-3">
                  {/* Summary */}
                  <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
                    <SummaryStat label="Added nodes"   value={diffResult.summary.added_nodes}   tone="emerald" />
                    <SummaryStat label="Removed nodes" value={diffResult.summary.removed_nodes} tone="rose" />
                    <SummaryStat label="Unchanged"     value={diffResult.summary.unchanged_nodes} tone="slate" />
                    <SummaryStat label="Added edges"   value={diffResult.summary.added_edges}   tone="emerald" />
                    <SummaryStat label="Removed edges" value={diffResult.summary.removed_edges} tone="rose" />
                  </div>
                  {/* By-type delta */}
                  {Object.keys(diffResult.summary.by_type_delta || {}).length > 0 && (
                    <div className="bg-white border border-[#E6E6E6] rounded-sm p-3">
                      <div className="text-[10px] uppercase font-bold text-[#747480] mb-1">Net change by type</div>
                      <div className="flex gap-2 flex-wrap">
                        {Object.entries(diffResult.summary.by_type_delta).map(([t, d]) => (
                          <span key={t} className={`text-[10px] px-1.5 py-0.5 rounded-sm font-mono ${d > 0 ? "bg-emerald-100 text-emerald-700" : d < 0 ? "bg-rose-100 text-rose-700" : "bg-slate-100 text-slate-600"}`}>
                            {t}: {d > 0 ? `+${d}` : d}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                  {/* Added / Removed lists */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <DiffNodeList title="Added" tone="emerald" nodes={diffResult.added_nodes} />
                    <DiffNodeList title="Removed" tone="rose" nodes={diffResult.removed_nodes} />
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function SummaryStat({ label, value, tone }) {
  const t = {
    emerald: "bg-emerald-50 border-emerald-200 text-emerald-700",
    rose:    "bg-rose-50 border-rose-200 text-rose-700",
    slate:   "bg-slate-50 border-slate-200 text-slate-600",
  }[tone] || "";
  return (
    <div className={`border rounded-sm p-2 ${t}`}>
      <div className="text-[9px] uppercase font-bold opacity-80">{label}</div>
      <div className="text-lg font-display font-bold leading-none mt-1">{value}</div>
    </div>
  );
}

function DiffNodeList({ title, tone, nodes }) {
  const t = tone === "emerald" ? "border-emerald-200 bg-emerald-50/30" : "border-rose-200 bg-rose-50/30";
  return (
    <div className={`border ${t} rounded-sm p-2`}>
      <div className="text-[10px] uppercase font-bold text-[#747480] mb-1">{title} ({nodes.length})</div>
      <div className="space-y-0.5 max-h-72 overflow-y-auto">
        {nodes.length === 0 && <div className="text-[11px] text-[#747480]">None.</div>}
        {nodes.map((n, i) => {
          const meta = TYPE_META[n.type] || {};
          return (
            <div key={i} className="flex items-center gap-1 text-[11px]" style={{ color: meta.color }}>
              <span className="text-[9px] uppercase font-bold w-12 truncate">{n.type}</span>
              <span className="font-mono truncate">{n.label}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
