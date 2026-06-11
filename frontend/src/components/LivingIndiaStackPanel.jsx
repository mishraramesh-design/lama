import React, { useEffect, useState, useCallback } from "react";
import { Sparkles, RefreshCw, Loader2, AlertTriangle, CheckCircle2 } from "lucide-react";
import { getIndiaStackLiving } from "@/lib/api";

function ScorePill({ score }) {
  const color = score >= 80 ? "#059669" : score >= 50 ? "#B45309" : "#B91C1C";
  const bg    = score >= 80 ? "#D1FAE5" : score >= 50 ? "#FEF3C7" : "#FEE2E2";
  return (
    <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-sm"
      style={{ color, background: bg }}>{score}%</span>
  );
}

export default function LivingIndiaStackPanel({ projectId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try { setData(await getIndiaStackLiving(projectId)); }
    finally { setLoading(false); }
  }, [projectId]);
  useEffect(() => { load(); }, [load]);

  if (loading && !data) return (
    <div className="p-6 flex items-center gap-2 text-[#747480] text-[11px]"
         data-testid="india-stack-living-loading">
      <Loader2 className="w-3 h-3 animate-spin" /> Loading India-Stack metrics…
    </div>
  );
  const rows = data?.rows || [];
  if (rows.length === 0) return (
    <div className="p-6 text-center text-[#747480] text-[11px]" data-testid="india-stack-living-empty">
      <Sparkles className="w-6 h-6 text-[#FFE600] mx-auto mb-2" />
      No India-Stack components selected yet. Go to <strong>Architecture → India Stack</strong> to pick some.
    </div>
  );

  return (
    <div className="bg-white border border-[#E6E6E6] rounded-sm" data-testid="india-stack-living">
      <div className="px-3 py-2 border-b border-[#E6E6E6] flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Sparkles className="w-3 h-3 text-[#FFE600]" />
          <h3 className="font-bold text-[12px] text-[#2E2E38]">India Stack — Living dashboard</h3>
        </div>
        <button onClick={load} data-testid="reload-india-stack-living"
          className="text-[10px] text-[#747480] hover:text-[#2E2E38] flex items-center gap-1">
          <RefreshCw className={`w-3 h-3 ${loading ? "animate-spin" : ""}`} /> Reload
        </button>
      </div>

      <div className="px-3 py-2 grid grid-cols-4 gap-2 border-b border-[#E6E6E6] bg-[#FAFAFC]">
        <Totals label="Components"   value={data.totals.components} />
        <Totals label="Total calls"  value={data.totals.calls} />
        <Totals label="Errors"       value={data.totals.errors}
          status={data.totals.errors > 0 ? "warn" : "ok"} />
        <Totals label="Avg compliance" value={`${data.totals.avg_compliance}%`}
          status={data.totals.avg_compliance >= 80 ? "ok" : "warn"} />
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-[11px]" data-testid="india-stack-living-table">
          <thead className="bg-[#FAFAFC] border-b border-[#E6E6E6]">
            <tr>
              <th className="text-left px-3 py-2 font-semibold text-[#747480] uppercase text-[9px] tracking-wider">Component</th>
              <th className="text-left px-3 py-2 font-semibold text-[#747480] uppercase text-[9px] tracking-wider">Mode</th>
              <th className="text-left px-3 py-2 font-semibold text-[#747480] uppercase text-[9px] tracking-wider">Attached to</th>
              <th className="text-right px-3 py-2 font-semibold text-[#747480] uppercase text-[9px] tracking-wider">Calls (7d)</th>
              <th className="text-right px-3 py-2 font-semibold text-[#747480] uppercase text-[9px] tracking-wider">Error %</th>
              <th className="text-center px-3 py-2 font-semibold text-[#747480] uppercase text-[9px] tracking-wider">Env</th>
              <th className="text-center px-3 py-2 font-semibold text-[#747480] uppercase text-[9px] tracking-wider">Compliance</th>
              <th className="text-center px-3 py-2 font-semibold text-[#747480] uppercase text-[9px] tracking-wider">Drift</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.component_id} className="border-b border-[#F0F0F4]"
                  data-testid={`india-row-${r.component_id}`}>
                <td className="px-3 py-2">
                  <div className="font-semibold">{r.name}</div>
                  <div className="text-[9px] text-[#747480]">{r.category}</div>
                </td>
                <td className="px-3 py-2">
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-sm font-bold ${
                    r.mode === "sandbox" ? "bg-[#D1FAE5] text-[#065F46]" : "bg-[#FEF3C7] text-[#92400E]"
                  }`}>{r.mode}{r.sandbox_provider ? ` · ${r.sandbox_provider}` : ""}</span>
                </td>
                <td className="px-3 py-2 font-mono text-[10px] text-[#2E2E38]">{r.attach_to}</td>
                <td className="px-3 py-2 text-right font-mono">{r.usage_total}</td>
                <td className="px-3 py-2 text-right font-mono">{r.error_rate}%</td>
                <td className="px-3 py-2 text-center text-[10px]">{r.env_filled}/{r.env_total}</td>
                <td className="px-3 py-2 text-center"><ScorePill score={r.compliance_score} /></td>
                <td className="px-3 py-2 text-center">
                  {r.drift_status === "ok"
                    ? <CheckCircle2 className="w-3 h-3 text-emerald-600 inline" />
                    : <AlertTriangle className="w-3 h-3 text-amber-600 inline" />}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Totals({ label, value, status }) {
  const colors = status === "warn" ? "text-amber-700" : status === "ok" ? "text-emerald-700" : "text-[#2E2E38]";
  return (
    <div>
      <div className="text-[9px] uppercase tracking-wider text-[#747480]">{label}</div>
      <div className={`text-base font-bold ${colors}`}>{value}</div>
    </div>
  );
}
