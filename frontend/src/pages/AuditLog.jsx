import React, { useEffect, useState } from "react";
import { listAudit } from "@/lib/api";
import { useProjects } from "@/state/ProjectContext";
import { Activity } from "lucide-react";

export default function AuditLogPage() {
  const { active } = useProjects();
  const [items, setItems] = useState([]);

  useEffect(() => {
    if (active?.id) listAudit(active.id).then(setItems);
  }, [active?.id]);

  return (
    <div className="flex-1 flex flex-col min-w-0">
      <header className="bg-white border-b border-slate-300 px-6 py-3">
        <div className="text-[10px] uppercase tracking-widest text-slate-500">Audit</div>
        <h1 className="font-display text-lg font-bold tracking-tight text-[#0A2540]">Audit Log</h1>
      </header>
      <div className="flex-1 overflow-y-auto mos-scroll p-6 bg-slate-100">
        <div className="max-w-3xl mx-auto mos-panel">
          {items.length === 0 ? (
            <div className="p-6 text-sm text-slate-500 text-center">
              <Activity className="w-5 h-5 mx-auto mb-2 text-slate-400" />
              No events yet.
            </div>
          ) : (
            <ul className="divide-y divide-slate-200">
              {items.map((it, i) => (
                <li key={i} className="px-4 py-3 flex items-center justify-between" data-testid={`audit-${i}`}>
                  <div>
                    <div className="text-sm font-mono text-[#0A2540]">{it.action}</div>
                    <div className="text-[11px] text-slate-500">{JSON.stringify(it.details || {})}</div>
                  </div>
                  <div className="text-[11px] text-slate-500">{new Date(it.at).toLocaleString()}</div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
