import React, { useState, useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { Lock, CheckCircle2, Circle, Library, BookOpen, Database, Boxes, Code2, Activity, Settings as SettingsIcon, ChevronLeft, ChevronRight } from "lucide-react";
import { useProjects } from "@/state/ProjectContext";
import { getPipelineStatus } from "@/lib/api";
import HelpIcon from "@/components/HelpIcon";
import { toast } from "sonner";

const STAGES = [
  { key: "Discovery", label: "1. Discovery & SRS", icon: BookOpen, desc: "Upload legacy files, ask gap questions, freeze SRS.", path: "/" },
  { key: "DataModel", label: "2. Data Model", icon: Database, desc: "OLTP + OLAP DDL, Bus Matrix, migration scripts.", path: "/data-model" },
  { key: "Architecture", label: "3. Architecture", icon: Boxes, desc: "Decompose into microservices.", path: "/" },
  { key: "CodeGen", label: "4. Code Generation", icon: Code2, desc: "Generate target code + unit tests.", path: "/" },
  { key: "Living", label: "5. Living System", icon: Activity, desc: "Selenium tests, SRS diffs, monitoring.", path: "/" },
];

export default function Sidebar() {
  const navigate = useNavigate();
  const location = useLocation();
  const { active } = useProjects();
  const [collapsed, setCollapsed] = useState(
    typeof window !== "undefined" && localStorage.getItem("lama:panel:sidebar") === "true"
  );
  const [pipeline, setPipeline] = useState({});

  useEffect(() => {
    if (!active?.id) return;
    let cancelled = false;
    const load = async () => {
      try {
        const data = await getPipelineStatus(active.id);
        if (!cancelled) setPipeline(data || {});
      } catch (_) { /* ignore */ }
    };
    load();
    const t = setInterval(load, 15000);
    return () => { cancelled = true; clearInterval(t); };
  }, [active?.id]);

  const toggle = () => {
    const v = !collapsed;
    localStorage.setItem("lama:panel:sidebar", String(v));
    setCollapsed(v);
  };

  // Resolve per-stage status combining project.stage_status + pipeline (StageContext)
  const stageStatus = (key, idx) => {
    const ctx = pipeline[key];
    if (ctx?.frozen) return "frozen";
    const projStatus = active?.stage_status?.[key];
    if (projStatus === "frozen") return "frozen";
    if (projStatus === "available") return "available";
    if (projStatus === "active") return "active";
    // Auto-promote: if previous stage is frozen, this one becomes "available"
    if (idx > 0) {
      const prev = STAGES[idx - 1];
      if (pipeline[prev.key]?.frozen || active?.stage_status?.[prev.key] === "frozen") {
        return "available";
      }
    }
    return projStatus || "locked";
  };

  // ----- Collapsed (rail) mode -----
  if (collapsed) {
    return (
      <aside
        data-testid="sidebar-collapsed"
        className="w-12 shrink-0 h-screen flex flex-col bg-white border-r border-[#E6E6E6]"
      >
        <button
          type="button"
          onClick={toggle}
          data-testid="expand-sidebar"
          className="w-9 h-9 m-1.5 bg-[#FFE600] text-[#2E2E38] flex items-center justify-center rounded-sm font-display font-bold text-base"
          aria-label="Expand sidebar"
        >
          L
        </button>
        <div className="flex flex-col items-center gap-1 mt-3">
          {STAGES.map((s, idx) => {
            const status = stageStatus(s.key, idx);
            const isLocked = status === "locked";
            const isFrozen = status === "frozen";
            const isCurrent = location.pathname === s.path && !isLocked;
            const Icon = s.icon;
            return (
              <button
                key={s.key}
                type="button"
                onClick={() => {
                  if (isLocked) {
                    toast.message("Locked", { description: `Complete and freeze previous stage to unlock ${s.label}.` });
                    return;
                  }
                  navigate(s.path);
                }}
                title={s.label}
                className={`w-9 h-9 flex items-center justify-center rounded-sm border ${
                  isLocked
                    ? "border-[#E6E6E6] bg-[#F6F6FA] text-[#747480] cursor-not-allowed"
                    : isCurrent
                    ? "border-[#2E2E38] bg-[#2E2E38] text-white"
                    : isFrozen
                    ? "border-[#FFE600] bg-[#FFFCE6] text-[#2E2E38]"
                    : "border-[#E6E6E6] hover:bg-[#F6F6FA] text-[#2E2E38]"
                }`}
              >
                {isFrozen ? <CheckCircle2 className="w-4 h-4" /> : isLocked ? <Lock className="w-3.5 h-3.5" /> : <Icon className="w-4 h-4" />}
              </button>
            );
          })}
        </div>
        <div className="mt-auto flex flex-col items-center gap-1 pb-2 border-t border-[#E6E6E6] pt-2">
          <button type="button" onClick={() => navigate("/prompts")} title="Prompt Library" className="w-9 h-9 flex items-center justify-center rounded-sm hover:bg-[#F6F6FA]">
            <Library className="w-4 h-4 text-[#747480]" />
          </button>
          <button type="button" onClick={() => navigate("/settings")} title="Settings & GitHub" className="w-9 h-9 flex items-center justify-center rounded-sm hover:bg-[#F6F6FA]">
            <SettingsIcon className="w-4 h-4 text-[#747480]" />
          </button>
          <button type="button" onClick={() => navigate("/audit")} title="Audit Log" className="w-9 h-9 flex items-center justify-center rounded-sm hover:bg-[#F6F6FA]">
            <Activity className="w-4 h-4 text-[#747480]" />
          </button>
          <button type="button" onClick={toggle} title="Expand sidebar" className="w-9 h-9 flex items-center justify-center rounded-sm hover:bg-[#F6F6FA] mt-1" data-testid="expand-sidebar-bottom">
            <ChevronRight className="w-4 h-4 text-[#2E2E38]" />
          </button>
        </div>
      </aside>
    );
  }

  return (
    <aside
      data-testid="sidebar"
      className="w-[260px] shrink-0 h-screen flex flex-col bg-white border-r border-[#E6E6E6]"
    >
      {/* Brand + Project (static, single-tenant) */}
      <div className="px-5 py-5 border-b border-[#E6E6E6]">
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-2">
            <div className="w-9 h-9 bg-[#FFE600] text-[#2E2E38] flex items-center justify-center rounded-sm font-display font-bold text-base">
              L
            </div>
            <div>
              <div className="font-display font-bold text-xl leading-none tracking-tight text-[#2E2E38]" data-testid="brand-name">LAMA</div>
              <div className="text-[10px] uppercase tracking-widest text-[#747480] mt-1 leading-tight">Legacy Application<br/>Modernization &amp; Alignment</div>
            </div>
          </div>
          <button
            type="button"
            onClick={toggle}
            data-testid="collapse-sidebar"
            className="text-[#747480] hover:text-[#2E2E38] p-1 -mr-1"
            aria-label="Collapse sidebar"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
        </div>
        {active && (
          <div data-testid="active-project-header">
            <div className="mos-label">Project</div>
            <div className="font-display font-bold text-sm text-slate-900 leading-tight mt-0.5" data-testid="active-project-name">{active.name}</div>
            <div className="text-[11px] text-slate-500 mt-1 leading-snug" data-testid="active-project-tech">
              {active.source_tech}
              <br />
              <span className="text-slate-400">→</span> {active.target_tech}
            </div>
          </div>
        )}
      </div>

      {/* Stage progress */}
      <div className="px-4 py-4 flex-1 overflow-y-auto mos-scroll">
        <div className="mos-label mb-3 flex items-center">
          Pipeline
          <HelpIcon text="The 5 stages of migration. Freeze each stage to advance. Stages 2-5 are coming soon." testId="help-pipeline" />
        </div>
        <nav className="space-y-1">
          {STAGES.map((s, idx) => {
            const status = stageStatus(s.key, idx);
            const ctx = pipeline[s.key];
            const isLocked = status === "locked";
            const isActive = status === "active";
            const isAvailable = status === "available";
            const isFrozen = status === "frozen";
            const isCurrent = location.pathname === s.path && !isLocked;
            const Icon = s.icon;
            return (
              <button
                key={s.key}
                data-testid={`stage-${s.key}`}
                onClick={() => {
                  if (isLocked) {
                    toast.message("Locked", { description: `Complete and freeze the previous stage to unlock ${s.label}.` });
                    return;
                  }
                  navigate(s.path);
                }}
                className={`w-full text-left flex items-start gap-2 px-2 py-2 rounded-sm border ${
                  isLocked
                    ? "border-[#E6E6E6] bg-slate-50 text-slate-400 cursor-not-allowed"
                    : isCurrent
                    ? "border-[#2E2E38] bg-[#2E2E38] text-white"
                    : isFrozen
                    ? "border-[#FFE600] bg-[#FFFCE6] text-[#2E2E38]"
                    : "border-[#E6E6E6] hover:bg-[#F6F6FA] text-slate-700"
                }`}
              >
                <div className="mt-0.5">
                  {isFrozen ? <CheckCircle2 className="w-4 h-4" /> : isLocked ? <Lock className="w-4 h-4" /> : <Icon className="w-4 h-4" />}
                </div>
                <div className="flex-1">
                  <div className="text-[13px] font-semibold flex items-center justify-between gap-1">
                    <span className="truncate">{s.label}</span>
                    {isFrozen && (
                      <span data-testid={`stage-${s.key}-badge-frozen`} className="text-[9px] uppercase bg-[#FFE600] text-[#2E2E38] px-1.5 py-0.5 rounded-sm tracking-wider font-bold shrink-0">
                        Frozen v{ctx?.version ?? "—"}
                      </span>
                    )}
                    {!isFrozen && isAvailable && (
                      <span data-testid={`stage-${s.key}-badge-ready`} className="text-[9px] uppercase bg-emerald-100 text-emerald-700 px-1.5 py-0.5 rounded-sm tracking-wider font-bold shrink-0">
                        Ready
                      </span>
                    )}
                    {!isFrozen && !isAvailable && isLocked && (
                      <span data-testid={`stage-${s.key}-badge-locked`} className="text-[9px] uppercase bg-slate-200 text-slate-600 px-1.5 py-0.5 rounded-sm tracking-wider shrink-0">Soon</span>
                    )}
                    {isActive && !isCurrent && !isFrozen && !isAvailable && (
                      <Circle className="w-2 h-2 fill-current text-[#FFE600]" />
                    )}
                  </div>
                  <div className={`text-[11px] mt-0.5 leading-snug ${isCurrent ? "text-white/80" : "text-slate-500"}`}>{s.desc}</div>
                </div>
              </button>
            );
          })}
        </nav>
      </div>

      {/* Bottom nav */}
      <div className="px-4 py-3 border-t border-[#E6E6E6] space-y-1">
        <button
          data-testid="nav-prompts"
          onClick={() => navigate("/prompts")}
          className={`w-full flex items-center gap-2 px-2 py-2 rounded-sm text-[13px] ${
            location.pathname === "/prompts" ? "bg-[#F6F6FA] text-[#2E2E38] font-semibold" : "text-slate-600 hover:bg-slate-50"
          }`}
        >
          <Library className="w-4 h-4" />
          Prompt Library
          <HelpIcon text="Global system prompts (admin) and per-project overrides for each stage." testId="help-prompts" />
        </button>
        <button
          data-testid="nav-settings"
          onClick={() => navigate("/settings")}
          className={`w-full flex items-center gap-2 px-2 py-2 rounded-sm text-[13px] ${
            location.pathname === "/settings" ? "bg-[#F6F6FA] text-[#2E2E38] font-semibold" : "text-slate-600 hover:bg-slate-50"
          }`}
        >
          <SettingsIcon className="w-4 h-4" />
          Settings &amp; GitHub
          <HelpIcon text="Configure GitHub repository and access token for pushing generated code." testId="help-settings" />
        </button>
        <button
          data-testid="nav-audit"
          onClick={() => navigate("/audit")}
          className={`w-full flex items-center gap-2 px-2 py-2 rounded-sm text-[13px] ${
            location.pathname === "/audit" ? "bg-[#F6F6FA] text-[#2E2E38] font-semibold" : "text-slate-600 hover:bg-slate-50"
          }`}
        >
          <Activity className="w-4 h-4" />
          Audit Log
        </button>
      </div>
    </aside>
  );
}
