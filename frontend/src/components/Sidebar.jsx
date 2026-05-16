import React, { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { Lock, CheckCircle2, Circle, Library, BookOpen, Database, Boxes, Code2, Activity, Plus, FolderKanban } from "lucide-react";
import { useProjects } from "@/state/ProjectContext";
import HelpIcon from "@/components/HelpIcon";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
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
  const { projects, activeId, setActiveId, active, create } = useProjects();
  const [newOpen, setNewOpen] = useState(false);
  const [form, setForm] = useState({ name: "", source_tech: "", target_tech: "" });

  const onCreate = async () => {
    if (!form.name) {
      toast.error("Project name required");
      return;
    }
    try {
      await create(form);
      toast.success("Project created");
      setNewOpen(false);
      setForm({ name: "", source_tech: "", target_tech: "" });
    } catch (e) {
      toast.error("Failed to create project");
    }
  };

  return (
    <aside
      data-testid="sidebar"
      className="w-[260px] shrink-0 h-screen flex flex-col bg-white border-r border-slate-300"
    >
      {/* Brand */}
      <div className="px-5 py-5 border-b border-slate-300">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-[#0A2540] text-white flex items-center justify-center rounded-sm font-display font-bold">
            M
          </div>
          <div>
            <div className="font-display font-bold text-[15px] leading-tight tracking-tight">MigrationOS</div>
            <div className="text-[10px] uppercase tracking-widest text-slate-500">Legacy → Modern</div>
          </div>
        </div>
      </div>

      {/* Project switcher */}
      <div className="px-4 py-4 border-b border-slate-300">
        <div className="flex items-center justify-between mb-2">
          <span className="mos-label flex items-center">
            <FolderKanban className="w-3 h-3 mr-1" />
            Project
            <HelpIcon text="Switch between migration projects. Each project has its own KB, SRS, and prompts." testId="help-project-switcher" />
          </span>
          <Dialog open={newOpen} onOpenChange={setNewOpen}>
            <DialogTrigger asChild>
              <button
                data-testid="new-project-btn"
                className="text-slate-500 hover:text-[#0A2540]"
                aria-label="New project"
              >
                <Plus className="w-4 h-4" />
              </button>
            </DialogTrigger>
            <DialogContent data-testid="new-project-dialog">
              <DialogHeader>
                <DialogTitle>New Migration Project</DialogTitle>
              </DialogHeader>
              <div className="space-y-3">
                <div>
                  <Label htmlFor="np-name">Name</Label>
                  <Input id="np-name" data-testid="np-name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
                </div>
                <div>
                  <Label htmlFor="np-source">Source Tech</Label>
                  <Input id="np-source" data-testid="np-source" placeholder="PHP 8 / CodeIgniter 4 / MariaDB" value={form.source_tech} onChange={(e) => setForm({ ...form, source_tech: e.target.value })} />
                </div>
                <div>
                  <Label htmlFor="np-target">Target Tech</Label>
                  <Input id="np-target" data-testid="np-target" placeholder="FastAPI / Python 3.12 / PostgreSQL" value={form.target_tech} onChange={(e) => setForm({ ...form, target_tech: e.target.value })} />
                </div>
              </div>
              <DialogFooter>
                <Button data-testid="np-submit" onClick={onCreate}>Create Project</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
        <select
          data-testid="project-selector"
          value={activeId || ""}
          onChange={(e) => setActiveId(e.target.value)}
          className="w-full bg-white border border-slate-300 rounded-sm px-2 py-2 text-sm focus:border-[#0A2540] focus:ring-1 focus:ring-[#0A2540] outline-none"
        >
          {projects.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
        {active && (
          <div className="mt-2 text-[11px] text-slate-500 leading-snug">
            <div><span className="font-medium text-slate-700">Source:</span> {active.source_tech}</div>
            <div><span className="font-medium text-slate-700">Target:</span> {active.target_tech}</div>
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
