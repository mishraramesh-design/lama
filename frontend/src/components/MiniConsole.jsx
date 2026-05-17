import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Terminal, ChevronDown, ChevronUp } from "lucide-react";
import { getUsageSummary } from "@/lib/api";

export default function MiniConsole({ stage, projectId }) {
  const lsKey = `lama:miniconsole:${stage}`;
  const [open, setOpen] = useState(() => localStorage.getItem(lsKey) !== "0");
  const [summary, setSummary] = useState(null);

  const refresh = async () => {
    if (!projectId) return;
    try { const r = await getUsageSummary(projectId, 1); setSummary(r); } catch { /* */ }
  };
  useEffect(() => { refresh(); const t = setInterval(refresh, 15000); return () => clearInterval(t); }, [projectId]); // eslint-disable-line

  const toggle = () => { const v = !open; setOpen(v); localStorage.setItem(lsKey, v ? "1" : "0"); };

  const stageRow = summary?.by_stage?.find((r) => r.stage === stage) || null;
  const totalTokens = summary?.total_tokens || 0;
  const totalCost = summary?.total_cost_usd || 0;

  if (!open) {
    return (
      <button
        onClick={toggle}
        data-testid="mini-console-collapsed"
        className="fixed bottom-0 right-0 z-30 h-7 px-3 bg-[#2E2E38] text-white text-[10px] flex items-center gap-2 rounded-tl-sm hover:bg-[#FFE600] hover:text-[#2E2E38] shadow"
      >
        <Terminal className="w-3 h-3" />
        <span>Console</span>
        <span className="text-[#FFE600] font-mono">{totalTokens.toLocaleString()}t</span>
        <ChevronUp className="w-3 h-3" />
      </button>
    );
  }

  return (
    <div
      data-testid="mini-console-expanded"
      className="fixed bottom-0 right-0 z-30 w-[360px] bg-white border-t border-l border-[#E6E6E6] rounded-tl-sm shadow-lg"
    >
      <div className="bg-[#2E2E38] text-white px-3 py-1.5 flex items-center justify-between">
        <div className="flex items-center gap-1 text-[11px] font-bold">
          <Terminal className="w-3 h-3 text-[#FFE600]" /> {stage} · Console
        </div>
        <button onClick={toggle} data-testid="mini-console-toggle" className="hover:text-[#FFE600]"><ChevronDown className="w-3 h-3" /></button>
      </div>
      <div className="p-3 grid grid-cols-2 gap-3 text-[11px]">
        <div>
          <div className="text-[9px] uppercase text-[#747480] font-bold">Stage usage (24h)</div>
          <div className="font-mono text-[#2E2E38] text-base font-bold">
            {(stageRow?.tokens || 0).toLocaleString()} <span className="text-[10px] text-[#747480]">tokens</span>
          </div>
          <div className="font-mono text-[10px] text-[#747480]">${(stageRow?.cost || 0).toFixed(4)}</div>
        </div>
        <div>
          <div className="text-[9px] uppercase text-[#747480] font-bold">All stages (24h)</div>
          <div className="font-mono text-[#2E2E38] text-base font-bold">
            {totalTokens.toLocaleString()} <span className="text-[10px] text-[#747480]">tokens</span>
          </div>
          <div className="font-mono text-[10px] text-[#747480]">${totalCost.toFixed(4)} · {summary?.total_runs || 0} runs</div>
        </div>
      </div>
      <div className="border-t border-[#E6E6E6] px-3 py-1.5 flex items-center justify-between text-[10px]">
        <Link to="/console?tab=agents" className="text-[#2E2E38] hover:text-[#FFE600] underline" data-testid="mini-console-open-agents">Open agents →</Link>
        <Link to="/console?tab=models" className="text-[#2E2E38] hover:text-[#FFE600] underline">Models →</Link>
      </div>
    </div>
  );
}
