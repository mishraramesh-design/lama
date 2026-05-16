import React from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { Lock, CheckCircle2, Circle, Library, BookOpen, Database, Boxes, Code2, Activity, Settings as SettingsIcon } from "lucide-react";
import { useProjects } from "@/state/ProjectContext";
import HelpIcon from "@/components/HelpIcon";
import { toast } from "sonner";

const STAGES = [
  { key: "Discovery", label: "1. Discovery & SRS", icon: BookOpen, desc: "Upload legacy files, ask gap questions, freeze SRS." },
  { key: "DataModel", label: "2. Data Model", icon: Database, desc: "Optimise schema for target stack." },
  { key: "Architecture", label: "3. Architecture", icon: Boxes, desc: "Decompose into microservices." },
  { key: "CodeGen", label: "4. Code Generation", icon: Code2, desc: "Generate target code + unit tests." },
  { key: "Living", label: "5. Living System", icon: Activity, desc: "Selenium tests, SRS diffs, monitoring." },
];

export default function Sidebar() {
  const navigate = useNavigate();
  const location = useLocation();
  const { active } = useProjects();

  return (
    <aside
      data-testid="sidebar"
      className="w-[260px] shrink-0 h-screen flex flex-col bg-white border-r border-slate-300"
    >
      {/* Brand + Project (static, single-tenant) */}
      <div className="px-5 py-5 border-b border-slate-300">
        <div className="flex items-center gap-2 mb-4">
          <div className="w-9 h-9 bg-[#0A2540] text-white flex items-center justify-center rounded-sm font-display font-bold text-base">
            L
          </div>
          <div>
            <div className="font-display font-bold text-xl leading-none tracking-tight text-[#0A2540]" data-testid="brand-name">LAMA</div>
            <div className="text-[10px] uppercase tracking-widest text-slate-500 mt-1 leading-tight">Legacy Application<br/>Modernization &amp; Alignment</div>
          </div>
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
            const status = active?.stage_status?.[s.key] || "locked";
            const isLocked = status === "locked";
            const isActive = status === "active";
            const isFrozen = status === "frozen";
            const isCurrent = location.pathname === "/" && idx === 0 && !isLocked;
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
                  navigate("/");
                }}
                className={`w-full text-left flex items-start gap-2 px-2 py-2 rounded-sm border ${
                  isLocked
                    ? "border-slate-200 bg-slate-50 text-slate-400 cursor-not-allowed"
                    : isCurrent
                    ? "border-[#0A2540] bg-[#0A2540] text-white"
                    : "border-slate-200 hover:bg-slate-100 text-slate-700"
                }`}
              >
                <div className="mt-0.5">
                  {isFrozen ? <CheckCircle2 className="w-4 h-4" /> : isLocked ? <Lock className="w-4 h-4" /> : <Icon className="w-4 h-4" />}
                </div>
                <div className="flex-1">
                  <div className="text-[13px] font-semibold flex items-center justify-between">
                    <span>{s.label}</span>
                    {isLocked && <span className="text-[9px] uppercase bg-slate-200 text-slate-600 px-1.5 py-0.5 rounded-sm tracking-wider">Soon</span>}
                    {isFrozen && <span className="text-[9px] uppercase bg-emerald-100 text-emerald-700 px-1.5 py-0.5 rounded-sm tracking-wider">Frozen</span>}
                    {isActive && !isCurrent && <Circle className="w-2 h-2 fill-current text-emerald-500" />}
                  </div>
                  <div className={`text-[11px] mt-0.5 leading-snug ${isCurrent ? "text-white/80" : "text-slate-500"}`}>{s.desc}</div>
                </div>
              </button>
            );
          })}
        </nav>
      </div>

      {/* Bottom nav */}
      <div className="px-4 py-3 border-t border-slate-300 space-y-1">
        <button
          data-testid="nav-prompts"
          onClick={() => navigate("/prompts")}
          className={`w-full flex items-center gap-2 px-2 py-2 rounded-sm text-[13px] ${
            location.pathname === "/prompts" ? "bg-slate-100 text-[#0A2540] font-semibold" : "text-slate-600 hover:bg-slate-50"
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
            location.pathname === "/settings" ? "bg-slate-100 text-[#0A2540] font-semibold" : "text-slate-600 hover:bg-slate-50"
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
            location.pathname === "/audit" ? "bg-slate-100 text-[#0A2540] font-semibold" : "text-slate-600 hover:bg-slate-50"
          }`}
        >
          <Activity className="w-4 h-4" />
          Audit Log
        </button>
      </div>
    </aside>
  );
}
