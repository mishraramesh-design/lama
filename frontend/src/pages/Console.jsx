import React, { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  Loader2,
  Sparkles,
  Trash2,
  Check,
  Plus,
  Cpu,
  Bot,
  FileText,
  Wand2,
  KeyRound,
  Terminal,
  Zap,
  ChevronDown,
  ChevronRight as ChevronRightIcon,
  RotateCcw,
  Play,
  TestTube,
} from "lucide-react";
import { toast } from "sonner";
import { useProjects } from "@/state/ProjectContext";
import {
  setupProvider, listProviders, updateProvider, updateProviderKey,
  deleteProvider, testProvider, fetchProviderModels,
  listAgents, updateAgent, resetAgentBudget, testAgent, getAgentUsage,
  getUsageSummary, listPrompts, previewPrompt, testPrompt, updateProjectPrompt,
} from "@/lib/api";
import { Button } from "@/components/ui/button";

const STAGES = ["Discovery", "DataModel", "Architecture", "CodeGen", "Living"];
const COMPLEXITY_COLOR = {
  low: "bg-emerald-100 text-emerald-700",
  medium: "bg-amber-100 text-amber-700",
  high: "bg-rose-100 text-rose-700",
};
const STATUS_COLOR = {
  enabled: "bg-emerald-100 text-emerald-700",
  disabled: "bg-slate-200 text-slate-600",
  replaced: "bg-violet-100 text-violet-700",
  wrapped: "bg-blue-100 text-blue-700",
};

// ============================================================
// Tab: Models
// ============================================================
function ModelsTab() {
  const [providers, setProviders] = useState([]);
  const [apiKey, setApiKey] = useState("");
  const [name, setName] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    try { const r = await listProviders(); setProviders(r.providers || []); } catch { /* */ }
  };
  useEffect(() => { refresh(); }, []);

  const onSetup = async () => {
    if (!apiKey.trim() && !baseUrl.trim()) {
      toast.error("Paste an API key (or a base URL for Ollama/custom).");
      return;
    }
    setBusy(true);
    try {
      const r = await setupProvider({ api_key: apiKey.trim(), name: name.trim(), base_url: baseUrl.trim() });
      toast.success(`Provider configured: ${r.provider?.name}`);
      setApiKey(""); setName(""); setBaseUrl("");
      await refresh();
    } catch (e) { toast.error("Setup failed: " + (e?.response?.data?.detail || e.message)); }
    finally { setBusy(false); }
  };

  return (
    <div className="space-y-5" data-testid="tab-models">
      {/* Quick setup */}
      <div className="bg-white border border-[#E6E6E6] rounded-sm overflow-hidden">
        <div className="bg-[#FFFCE6] border-l-4 border-[#FFE600] px-4 py-3">
          <div className="text-[10px] uppercase font-bold tracking-wider text-[#747480]">Quick Setup</div>
          <div className="text-sm font-display font-bold text-[#2E2E38]">Paste one API key to configure routing automatically</div>
          <div className="text-[11px] text-[#747480] mt-0.5">Auto-detects provider from key prefix (sk-or- → OpenRouter, sk-ant- → Anthropic, sk- → OpenAI, gsk_ → Groq).</div>
        </div>
        <div className="p-4 grid grid-cols-1 lg:grid-cols-3 gap-3">
          <input
            data-testid="setup-api-key"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="sk-or-... / sk-ant-... / sk-... / gsk_..."
            className="text-[12px] font-mono border border-[#E6E6E6] focus:border-[#2E2E38] outline-none rounded-sm px-2 py-2 lg:col-span-2"
          />
          <input
            data-testid="setup-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Name (optional)"
            className="text-[12px] border border-[#E6E6E6] focus:border-[#2E2E38] outline-none rounded-sm px-2 py-2"
          />
          <input
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="Custom base URL (optional)"
            className="text-[12px] font-mono border border-[#E6E6E6] focus:border-[#2E2E38] outline-none rounded-sm px-2 py-2 lg:col-span-2"
          />
          <Button data-testid="setup-btn" onClick={onSetup} disabled={busy} className="bg-[#FFE600] text-[#2E2E38] hover:bg-[#FFD500] font-bold">
            {busy ? <Loader2 className="w-3 h-3 animate-spin" /> : <Wand2 className="w-3 h-3" />} Auto-configure
          </Button>
        </div>
      </div>

      {/* Provider cards */}
      {providers.length === 0 && (
        <div className="text-center py-12 text-[#747480] border border-dashed border-[#E6E6E6] rounded-sm">
          <KeyRound className="w-8 h-8 mx-auto mb-2 text-[#FFE600]" />
          <div className="text-sm">No provider configured yet — paste a key above.</div>
          <div className="text-[11px] mt-1">Without a provider, LAMA falls back to the legacy <code>OPENROUTER_API_KEY</code> env var.</div>
        </div>
      )}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        {providers.map((p) => <ProviderCard key={p.id} provider={p} refresh={refresh} />)}
      </div>
    </div>
  );
}

function ProviderCard({ provider, refresh }) {
  const [editingKey, setEditingKey] = useState(false);
  const [newKey, setNewKey] = useState("");
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);

  const onDelete = async () => {
    if (!window.confirm(`Delete provider "${provider.name}"?`)) return;
    try { await deleteProvider(provider.id); toast.success("Deleted"); refresh(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Delete failed"); }
  };
  const onTest = async () => {
    setTesting(true); setTestResult(null);
    try { const r = await testProvider(provider.id); setTestResult(r); }
    catch (e) { setTestResult({ ok: false, error: e.message }); }
    finally { setTesting(false); }
  };
  const onFetch = async () => {
    try { const r = await fetchProviderModels(provider.id); toast.success(`Fetched ${r.count || 0} models`); refresh(); }
    catch (e) { toast.error("Fetch failed"); }
  };
  const onSaveKey = async () => {
    try { await updateProviderKey(provider.id, newKey); toast.success("Key updated"); setEditingKey(false); setNewKey(""); refresh(); }
    catch (e) { toast.error("Update failed"); }
  };
  const onSetDefault = async () => {
    try { await updateProvider(provider.id, { is_default: true }); toast.success("Set as default"); refresh(); }
    catch { toast.error("Failed"); }
  };
  const onRoutingChange = async (tier, modelId) => {
    const routing = { ...(provider.routing || {}), [tier]: modelId };
    try { await updateProvider(provider.id, { routing }); refresh(); }
    catch { toast.error("Routing update failed"); }
  };

  return (
    <div className="bg-white border border-[#E6E6E6] rounded-sm p-3" data-testid={`provider-${provider.id}`}>
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <Cpu className="w-3 h-3 text-[#747480]" />
            <span className="font-display font-bold text-[#2E2E38] truncate">{provider.name}</span>
            <span className="text-[9px] uppercase font-bold bg-[#F6F6FA] px-1 py-0.5 rounded-sm">{provider.provider_type}</span>
            {provider.is_default && <span className="text-[9px] uppercase font-bold bg-[#FFE600] text-[#2E2E38] px-1 py-0.5 rounded-sm">Default</span>}
          </div>
          <div className="text-[11px] text-[#747480] font-mono truncate">{provider.base_url}</div>
          <div className="text-[11px] text-[#747480] font-mono">Key: {provider.api_key}</div>
        </div>
        <button onClick={onDelete} data-testid={`delete-provider-${provider.id}`} title="Delete" className="p-1 text-rose-500 hover:bg-rose-50 rounded-sm">
          <Trash2 className="w-3 h-3" />
        </button>
      </div>

      {/* Routing table */}
      <div className="mt-3 border-t border-[#E6E6E6] pt-2">
        <div className="text-[10px] uppercase font-bold text-[#747480] mb-1">Routing</div>
        {["low", "medium", "high"].map((tier) => (
          <div key={tier} className="flex items-center gap-2 mb-1">
            <span className={`text-[10px] uppercase font-bold px-1.5 py-0.5 rounded-sm w-16 text-center ${COMPLEXITY_COLOR[tier]}`}>{tier}</span>
            <select
              data-testid={`routing-${provider.id}-${tier}`}
              value={provider.routing?.[tier] || ""}
              onChange={(e) => onRoutingChange(tier, e.target.value)}
              className="flex-1 text-[11px] border border-[#E6E6E6] rounded-sm px-1 py-0.5"
            >
              <option value="">— select —</option>
              {(provider.models || []).map((m) => <option key={m.id} value={m.id}>{m.label || m.id}</option>)}
            </select>
          </div>
        ))}
      </div>

      {/* Buttons */}
      <div className="mt-3 flex flex-wrap gap-1">
        <button onClick={onTest} disabled={testing} data-testid={`test-provider-${provider.id}`} className="text-[10px] px-2 py-1 border border-[#E6E6E6] rounded-sm hover:bg-[#F6F6FA] flex items-center gap-1">
          {testing ? <Loader2 className="w-3 h-3 animate-spin" /> : <TestTube className="w-3 h-3" />} Test
        </button>
        <button onClick={onFetch} className="text-[10px] px-2 py-1 border border-[#E6E6E6] rounded-sm hover:bg-[#F6F6FA] flex items-center gap-1">
          <Plus className="w-3 h-3" /> Fetch models
        </button>
        {!provider.is_default && (
          <button onClick={onSetDefault} className="text-[10px] px-2 py-1 border border-[#E6E6E6] rounded-sm hover:bg-[#F6F6FA]">Set as default</button>
        )}
        <button onClick={() => setEditingKey(!editingKey)} className="text-[10px] px-2 py-1 border border-[#E6E6E6] rounded-sm hover:bg-[#F6F6FA]">Edit key</button>
      </div>
      {editingKey && (
        <div className="mt-2 flex gap-1">
          <input value={newKey} onChange={(e) => setNewKey(e.target.value)} placeholder="New API key" className="flex-1 text-[11px] border border-[#E6E6E6] rounded-sm px-2 py-1 font-mono" />
          <button onClick={onSaveKey} className="text-[11px] px-2 py-1 bg-[#2E2E38] text-white rounded-sm">Save</button>
        </div>
      )}
      {testResult && (
        <div className={`mt-2 text-[11px] p-2 rounded-sm ${testResult.ok ? "bg-emerald-50 border border-emerald-200 text-emerald-800" : "bg-rose-50 border border-rose-200 text-rose-700"}`}>
          {testResult.ok
            ? `✓ ${testResult.model_used} · ${testResult.latency_ms}ms · "${testResult.response}"`
            : `✗ ${testResult.error}`}
        </div>
      )}
      {(provider.models || []).length > 0 && (
        <details className="mt-2">
          <summary className="text-[10px] uppercase font-bold text-[#747480] cursor-pointer">Catalogue ({provider.models.length})</summary>
          <div className="mt-1 space-y-0.5">
            {provider.models.map((m) => (
              <div key={m.id} className="text-[10px] text-[#2E2E38] flex justify-between font-mono">
                <span className="truncate">{m.id}</span>
                {m.cost_per_1k_input != null && <span className="text-[#747480]">in ${m.cost_per_1k_input}/1k · out ${m.cost_per_1k_output}/1k</span>}
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

// ============================================================
// Tab: Agents
// ============================================================
function AgentsTab() {
  const { active } = useProjects();
  const projectId = active?.id;
  const [data, setData] = useState({});
  const [openStages, setOpenStages] = useState(() => Object.fromEntries(STAGES.map((s) => [s, true])));
  const [openAgent, setOpenAgent] = useState(null);

  const refresh = async () => { try { const r = await listAgents(); setData(r || {}); } catch { /* */ } };
  useEffect(() => { refresh(); }, []);

  return (
    <div className="space-y-3" data-testid="tab-agents">
      <div className="text-[11px] text-[#747480]">
        Every LLM call in LAMA flows through one of these agents. Override model, disable, wrap, or replace per agent — changes apply to the very next run.
      </div>
      {STAGES.map((stage) => {
        const bucket = data[stage] || { orchestrator: [], tasks: [] };
        const isOpen = openStages[stage];
        const all = [...(bucket.orchestrator || []), ...(bucket.tasks || [])];
        if (all.length === 0) return null;
        return (
          <div key={stage} className="bg-white border border-[#E6E6E6] rounded-sm" data-testid={`stage-block-${stage}`}>
            <button onClick={() => setOpenStages((p) => ({ ...p, [stage]: !p[stage] }))} className="w-full flex items-center gap-2 px-3 py-2 hover:bg-[#F6F6FA]">
              {isOpen ? <ChevronDown className="w-3 h-3" /> : <ChevronRightIcon className="w-3 h-3" />}
              <span className="font-display font-bold text-[13px] text-[#2E2E38]">{stage}</span>
              <span className="text-[10px] text-[#747480]">({all.length} agents)</span>
            </button>
            {isOpen && (
              <div className="border-t border-[#E6E6E6]">
                {all.map((a) => (
                  <AgentRow
                    key={a.key}
                    agent={a}
                    expanded={openAgent === a.key}
                    onToggle={() => setOpenAgent(openAgent === a.key ? null : a.key)}
                    projectId={projectId}
                    onChange={refresh}
                  />
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function AgentRow({ agent, expanded, onToggle, projectId, onChange }) {
  const [draft, setDraft] = useState(agent);
  const [testResult, setTestResult] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { setDraft(agent); }, [agent.key, agent.updated_at]); // eslint-disable-line

  const save = async (patch) => {
    try { await updateAgent(agent.key, patch); toast.success("Saved"); onChange(); }
    catch (e) { toast.error("Save failed: " + (e?.response?.data?.detail || e.message)); }
  };

  const onTest = async () => {
    setBusy(true); setTestResult(null);
    try {
      const r = await testAgent(agent.key, projectId);
      setTestResult(r);
    } catch (e) { setTestResult({ ok: false, error: e.message }); }
    finally { setBusy(false); }
  };

  const onResetBudget = async () => {
    try { await resetAgentBudget(agent.key); toast.success("Budget reset"); onChange(); } catch { toast.error("Reset failed"); }
  };

  return (
    <div className="border-b border-[#F6F6FA] last:border-b-0" data-testid={`agent-row-${agent.key}`}>
      <button onClick={onToggle} className="w-full flex items-center gap-2 px-3 py-2 hover:bg-[#FAFAFC] text-left">
        {expanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRightIcon className="w-3 h-3" />}
        {agent.agent_type === "orchestrator" ? <Zap className="w-3 h-3 text-[#FFE600]" /> : <Bot className="w-3 h-3 text-[#747480]" />}
        <div className="flex-1 min-w-0">
          <div className="text-[12px] font-semibold text-[#2E2E38] truncate">{agent.label} <span className="text-[#747480] font-mono font-normal">· {agent.key}</span></div>
          <div className="text-[10px] text-[#747480] truncate">{agent.description}</div>
        </div>
        <span className={`text-[9px] uppercase font-bold px-1.5 py-0.5 rounded-sm ${COMPLEXITY_COLOR[agent.complexity] || ""}`}>{agent.complexity}</span>
        <span className={`text-[9px] uppercase font-bold px-1.5 py-0.5 rounded-sm ${STATUS_COLOR[agent.status] || ""}`}>{agent.status}</span>
        <span className="text-[10px] text-[#747480] font-mono whitespace-nowrap hidden md:inline">
          ↑ {(agent.tokens_used_last_run || 0).toLocaleString()} · ${(agent.last_run_cost_usd || 0).toFixed(4)}
        </span>
      </button>
      {expanded && (
        <div className="px-4 pb-3 pt-1 bg-[#FAFAFC]">
          <div className="text-[10px] text-[#747480] mb-2">Resolved: <span className="font-mono text-[#2E2E38]">{agent.resolved_model || "(no model)"}</span> via {agent.resolved_provider}</div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
            <Field label="Complexity">
              <select data-testid={`agent-${agent.key}-complexity`} value={draft.complexity || "medium"} onChange={(e) => save({ complexity: e.target.value })} className="w-full text-[11px] border border-[#E6E6E6] rounded-sm px-1 py-1">
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
              </select>
            </Field>
            <Field label="Model override">
              <input
                data-testid={`agent-${agent.key}-override`}
                value={draft.model_override || ""}
                onChange={(e) => setDraft({ ...draft, model_override: e.target.value })}
                onBlur={() => draft.model_override !== agent.model_override && save({ model_override: draft.model_override })}
                placeholder="(routing-based)"
                className="w-full text-[11px] font-mono border border-[#E6E6E6] rounded-sm px-1 py-1"
              />
            </Field>
            <Field label="Status">
              <select data-testid={`agent-${agent.key}-status`} value={draft.status} onChange={(e) => save({ status: e.target.value })} className="w-full text-[11px] border border-[#E6E6E6] rounded-sm px-1 py-1">
                <option value="enabled">Enabled</option>
                <option value="disabled">Disabled</option>
                <option value="wrapped">Wrapped</option>
                <option value="replaced">Replaced</option>
              </select>
            </Field>
            <Field label="Max tokens">
              <input
                type="number" min={128}
                value={draft.max_tokens}
                onChange={(e) => setDraft({ ...draft, max_tokens: parseInt(e.target.value) || 0 })}
                onBlur={() => draft.max_tokens !== agent.max_tokens && save({ max_tokens: draft.max_tokens })}
                className="w-full text-[11px] border border-[#E6E6E6] rounded-sm px-1 py-1"
              />
            </Field>
            <Field label="Temperature">
              <input
                type="number" step={0.05} min={0} max={2}
                value={draft.temperature}
                onChange={(e) => setDraft({ ...draft, temperature: parseFloat(e.target.value) || 0 })}
                onBlur={() => draft.temperature !== agent.temperature && save({ temperature: draft.temperature })}
                className="w-full text-[11px] border border-[#E6E6E6] rounded-sm px-1 py-1"
              />
            </Field>
            <Field label="Total budget (0 = unlimited)">
              <div className="flex gap-1">
                <input
                  type="number" min={0}
                  value={draft.token_budget_total}
                  onChange={(e) => setDraft({ ...draft, token_budget_total: parseInt(e.target.value) || 0 })}
                  onBlur={() => draft.token_budget_total !== agent.token_budget_total && save({ token_budget_total: draft.token_budget_total })}
                  className="flex-1 text-[11px] border border-[#E6E6E6] rounded-sm px-1 py-1"
                />
                <button onClick={onResetBudget} title="Reset usage counter" className="text-[10px] px-1 border border-[#E6E6E6] rounded-sm hover:bg-white">
                  <RotateCcw className="w-3 h-3" />
                </button>
              </div>
            </Field>
          </div>

          {draft.status === "wrapped" && (
            <div className="mt-2 space-y-1">
              <Field label="Wrap prefix">
                <textarea rows={2} value={draft.wrap_prefix || ""} onChange={(e) => setDraft({ ...draft, wrap_prefix: e.target.value })} onBlur={() => save({ wrap_prefix: draft.wrap_prefix })} className="w-full text-[11px] font-mono border border-[#E6E6E6] rounded-sm px-1 py-1" />
              </Field>
              <Field label="Wrap suffix">
                <textarea rows={2} value={draft.wrap_suffix || ""} onChange={(e) => setDraft({ ...draft, wrap_suffix: e.target.value })} onBlur={() => save({ wrap_suffix: draft.wrap_suffix })} className="w-full text-[11px] font-mono border border-[#E6E6E6] rounded-sm px-1 py-1" />
              </Field>
            </div>
          )}
          {draft.status === "replaced" && (
            <div className="mt-2">
              <Field label="Replacement template">
                <textarea rows={4} value={draft.replaced_template || ""} onChange={(e) => setDraft({ ...draft, replaced_template: e.target.value })} onBlur={() => save({ replaced_template: draft.replaced_template })} className="w-full text-[11px] font-mono border border-[#E6E6E6] rounded-sm px-1 py-1" />
              </Field>
            </div>
          )}
          {draft.status === "disabled" && (
            <div className="mt-2 text-[11px] bg-amber-50 border border-amber-200 rounded-sm p-2 text-amber-800">
              <strong>Warning:</strong> This agent will be skipped. The pipeline step it performs will not execute.
            </div>
          )}

          <div className="mt-3 flex items-center gap-2">
            <Button onClick={onTest} disabled={busy} data-testid={`agent-${agent.key}-test`} className="h-7 text-[11px] bg-[#FFE600] text-[#2E2E38] hover:bg-[#FFD500]">
              {busy ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />} Test
            </Button>
            <span className="text-[10px] text-[#747480]">Tokens all-time: {(agent.tokens_used_all_time || 0).toLocaleString()}</span>
          </div>
          {testResult && (
            <div className={`mt-2 text-[11px] p-2 rounded-sm ${testResult.ok ? "bg-emerald-50 border border-emerald-200" : "bg-rose-50 border border-rose-200 text-rose-700"}`}>
              {testResult.ok ? (
                <>
                  <div><strong>{testResult.model_used}</strong> · ↑ {testResult.usage?.prompt_tokens} ↓ {testResult.usage?.completion_tokens} · ${testResult.cost_usd?.toFixed?.(4)}</div>
                  <pre className="mt-1 whitespace-pre-wrap text-[#2E2E38]">{testResult.content_preview}</pre>
                </>
              ) : `✗ ${testResult.error}`}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="text-[10px] uppercase font-bold text-[#747480]">{label}</span>
      <div className="mt-0.5">{children}</div>
    </label>
  );
}

// ============================================================
// Tab: Prompts (engineering — preview + test)
// ============================================================
function PromptsTab() {
  const { active } = useProjects();
  const projectId = active?.id;
  const [prompts, setPrompts] = useState([]);
  const [selected, setSelected] = useState(null);
  const [template, setTemplate] = useState("");
  const [preview, setPreview] = useState(null);
  const [running, setRunning] = useState(false);
  const [testOut, setTestOut] = useState(null);

  const refresh = async () => { try { const r = await listPrompts(); setPrompts(r.prompts || r || []); } catch { /* */ } };
  useEffect(() => { refresh(); }, []);

  const onSelect = async (p) => {
    setSelected(p); setTemplate(p.template || ""); setPreview(null); setTestOut(null);
    if (projectId) {
      try { const pr = await previewPrompt(p.key, projectId); setPreview(pr); } catch { /* */ }
    }
  };

  const grouped = useMemo(() => {
    const out = {};
    for (const p of prompts) {
      const stage = (p.key || "").split(".")[0];
      const stageMap = { srs: "Discovery", datamodel: "DataModel", arch: "Architecture", codegen: "CodeGen" };
      const s = stageMap[stage] || "Other";
      out[s] = out[s] || [];
      out[s].push(p);
    }
    return out;
  }, [prompts]);

  const onSave = async () => {
    if (!selected || !projectId) return;
    try {
      await updateProjectPrompt(projectId, selected.key, { template });
      toast.success("Project override saved");
      refresh();
    } catch { toast.error("Save failed"); }
  };

  const onTest = async () => {
    if (!selected) return;
    setRunning(true); setTestOut(null);
    try { const r = await testPrompt(selected.key, projectId); setTestOut(r); }
    catch (e) { setTestOut({ ok: false, error: e.message }); }
    finally { setRunning(false); }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-3 min-h-[600px]" data-testid="tab-prompts">
      {/* List */}
      <div className="lg:col-span-3 bg-white border border-[#E6E6E6] rounded-sm overflow-hidden">
        <div className="px-3 py-2 border-b border-[#E6E6E6] text-[10px] uppercase font-bold text-[#747480]">Prompts</div>
        <div className="overflow-y-auto max-h-[600px]">
          {Object.entries(grouped).map(([stage, list]) => (
            <div key={stage}>
              <div className="text-[10px] uppercase text-[#747480] bg-[#F6F6FA] px-3 py-1 font-bold">{stage}</div>
              {list.map((p) => (
                <button
                  key={p.key}
                  data-testid={`prompt-${p.key}`}
                  onClick={() => onSelect(p)}
                  className={`w-full text-left px-3 py-1.5 text-[11px] font-mono border-l-2 ${selected?.key === p.key ? "border-[#FFE600] bg-[#FFFCE6]" : "border-transparent hover:bg-[#F6F6FA]"}`}
                >
                  {p.key}
                </button>
              ))}
            </div>
          ))}
        </div>
      </div>

      {/* Editor */}
      <div className="lg:col-span-5 bg-white border border-[#E6E6E6] rounded-sm flex flex-col">
        <div className="px-3 py-2 border-b border-[#E6E6E6] flex items-center gap-2">
          <FileText className="w-3 h-3 text-[#747480]" />
          <span className="text-[12px] font-mono">{selected?.key || "Select a prompt"}</span>
          {selected && (
            <span className="text-[9px] uppercase bg-[#F6F6FA] px-1 py-0.5 rounded-sm ml-auto">v{selected.version || 1}</span>
          )}
        </div>
        <textarea
          value={template}
          onChange={(e) => setTemplate(e.target.value)}
          data-testid="prompt-editor"
          placeholder="Pick a prompt on the left to edit its project override…"
          className="flex-1 text-[11px] font-mono p-3 outline-none resize-none min-h-[400px]"
        />
        <div className="border-t border-[#E6E6E6] px-3 py-2 flex items-center gap-2">
          <span className="text-[10px] text-[#747480]">{template.length} chars · ~{Math.max(1, Math.floor(template.length / 4))} tokens</span>
          <div className="ml-auto flex gap-1">
            <Button data-testid="prompt-test" onClick={onTest} disabled={!selected || running} className="h-7 text-[11px]" variant="outline">
              {running ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />} Test
            </Button>
            <Button data-testid="prompt-save" onClick={onSave} disabled={!selected || !projectId} className="h-7 text-[11px] bg-[#2E2E38] text-white">Save override</Button>
          </div>
        </div>
      </div>

      {/* Preview */}
      <div className="lg:col-span-4 bg-white border border-[#E6E6E6] rounded-sm overflow-hidden">
        <div className="px-3 py-2 border-b border-[#E6E6E6] text-[10px] uppercase font-bold text-[#747480]">Live preview (current KB)</div>
        <div className="p-3 space-y-2 overflow-y-auto max-h-[600px]">
          {!preview && <div className="text-[11px] text-[#747480]">Select a prompt to resolve variables against the current project.</div>}
          {preview && (
            <>
              <div className="text-[11px] grid grid-cols-2 gap-1">
                <div><span className="text-[#747480]">Tokens:</span> <strong>{preview.total_token_estimate.toLocaleString()}</strong></div>
                <div><span className="text-[#747480]">Cost:</span> <strong>${preview.cost_estimate_usd.toFixed(6)}</strong></div>
                <div className="col-span-2"><span className="text-[#747480]">Model:</span> <strong className="font-mono">{preview.model_that_will_run || "(no provider)"}</strong></div>
              </div>
              <div className="border-t border-[#E6E6E6] pt-2 space-y-1">
                <div className="text-[10px] uppercase font-bold text-[#747480]">Variables</div>
                {preview.variables.map((v) => (
                  <div key={v.name} className="text-[11px] border border-[#F6F6FA] rounded-sm p-1.5">
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-[#2E2E38]">{`{${v.name}}`}</span>
                      <span className="text-[9px] text-[#747480]">~{v.token_estimate} tok</span>
                    </div>
                    <div className="text-[10px] text-[#747480] mt-0.5 truncate">{v.resolved}</div>
                  </div>
                ))}
              </div>
              {testOut && (
                <div className={`mt-2 text-[11px] p-2 rounded-sm ${testOut.ok ? "bg-emerald-50 border border-emerald-200" : "bg-rose-50 border border-rose-200 text-rose-700"}`}>
                  {testOut.ok ? (
                    <>
                      <div><strong>{testOut.model_used}</strong> · ↑ {testOut.usage?.prompt_tokens} ↓ {testOut.usage?.completion_tokens} · ${testOut.cost_usd?.toFixed?.(4)} · {testOut.duration_ms}ms</div>
                      <pre className="mt-1 whitespace-pre-wrap text-[#2E2E38] max-h-40 overflow-y-auto">{testOut.content}</pre>
                    </>
                  ) : `✗ ${testOut.error}`}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ============================================================
// Main page
// ============================================================
export default function ConsolePage() {
  const [params] = useSearchParams();
  const [tab, setTab] = useState(params.get("tab") || "models");
  return (
    <div className="flex-1 flex flex-col min-w-0 bg-[#F6F6FA]" data-testid="console-page">
      <header className="bg-white border-b-2 border-[#FFE600] px-6 py-3">
        <div className="text-[10px] uppercase tracking-widest text-[#747480]">LAMA Console</div>
        <h1 className="font-display text-lg font-bold tracking-tight text-[#2E2E38] flex items-center gap-2">
          <Terminal className="w-4 h-4 text-[#FFE600]" /> Model Fabric · Agent Fabric · Prompt Engineering
        </h1>
        <div className="mt-3 flex gap-1">
          {[
            { id: "models", label: "Models", icon: Cpu },
            { id: "agents", label: "Agents", icon: Bot },
            { id: "prompts", label: "Prompts", icon: FileText },
          ].map((t) => (
            <button
              key={t.id}
              data-testid={`console-tab-${t.id}`}
              onClick={() => setTab(t.id)}
              className={`flex items-center gap-1 text-[12px] px-3 py-1.5 border-b-2 ${tab === t.id ? "border-[#FFE600] text-[#2E2E38] font-bold" : "border-transparent text-[#747480]"}`}
            >
              <t.icon className="w-3 h-3" /> {t.label}
            </button>
          ))}
        </div>
      </header>
      <div className="flex-1 overflow-y-auto mos-scroll p-6">
        {tab === "models" && <ModelsTab />}
        {tab === "agents" && <AgentsTab />}
        {tab === "prompts" && <PromptsTab />}
      </div>
    </div>
  );
}
