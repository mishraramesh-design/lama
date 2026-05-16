import React, { useEffect, useState, useRef, useCallback } from "react";
import { Send, Bot, User, Cpu, Pencil } from "lucide-react";
import { chatHistory, sendMessage, listModels, kbGlossary, updateSRSSection } from "@/lib/api";
import HelpIcon from "@/components/HelpIcon";
import { toast } from "sonner";

const SECTION_OPTIONS = [
  { value: "purpose", label: "1. Purpose" },
  { value: "scope", label: "2. Scope" },
  { value: "definitions", label: "3. Definitions" },
  { value: "overall_description", label: "4. Overall Description" },
  { value: "functional_requirements", label: "5. Functional Requirements" },
  { value: "non_functional_requirements", label: "6. Non-Functional Requirements" },
  { value: "use_cases", label: "7. Use Cases" },
  { value: "constraints", label: "8. Constraints" },
];

export default function ChatPanel({ projectId, kbReady, onConversationUpdated }) {
  const [history, setHistory] = useState([]);
  const [input, setInput] = useState("");
  const [model, setModel] = useState("deepseek/deepseek-chat");
  const [models, setModels] = useState([]);
  const [conversationId, setConversationId] = useState(null);
  const [sending, setSending] = useState(false);
  const [tokens, setTokens] = useState(0);
  const [glossary, setGlossary] = useState([]);
  const [suggestions, setSuggestions] = useState([]);
  const [srsEditMode, setSrsEditMode] = useState(false);
  const [editSection, setEditSection] = useState("functional_requirements");
  const scrollRef = useRef(null);

  useEffect(() => {
    listModels().then((d) => setModels(d.models)).catch(() => {});
  }, []);

  useEffect(() => {
    if (!projectId) return;
    chatHistory(projectId).then((msgs) => {
      setHistory(msgs);
      if (msgs.length > 0) setConversationId(msgs[0].conversation_id);
      setTokens(msgs.reduce((acc, m) => acc + (m.tokens || 0), 0));
    });
    kbGlossary(projectId).then((d) => setGlossary(d.terms || []));
  }, [projectId, kbReady]);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [history]);

  const onInputChange = (v) => {
    setInput(v);
    if (v.length >= 2) {
      const q = v.toLowerCase();
      const matches = glossary
        .filter((t) => t.toLowerCase().includes(q))
        .slice(0, 6);
      setSuggestions(matches);
    } else {
      setSuggestions([]);
    }
  };

  const send = useCallback(async () => {
    if (!input.trim() || sending) return;
    const text = input;
    setInput("");
    setSuggestions([]);
    setSending(true);
    // optimistic
    const userMsg = { role: "user", content: text, created_at: new Date().toISOString(), tokens: Math.ceil(text.length / 4) };
    setHistory((h) => [...h, userMsg]);
    try {
      const r = await sendMessage({
        project_id: projectId,
        message: text,
        model,
        stage: "Discovery",
        conversation_id: conversationId,
        edit_mode: srsEditMode,
        selected_section: srsEditMode ? editSection : null,
      });
      setConversationId(r.conversation_id);
      // Tag the response so we can render the "Apply to SRS" button for edit responses
      const enrichedMsg = srsEditMode
        ? { ...r.message, _editSection: editSection }
        : r.message;
      setHistory((h) => [...h, enrichedMsg]);
      setTokens((t) => t + (r.usage?.total_tokens || 0));
      onConversationUpdated?.(r.conversation_id, r.srs_triggered);
    } catch (e) {
      toast.error("Chat failed", { description: e.response?.data?.detail || e.message });
      setHistory((h) => h.slice(0, -1));
      setInput(text);
    } finally {
      setSending(false);
    }
  }, [input, sending, projectId, model, conversationId, srsEditMode, editSection, onConversationUpdated]);

  const applySrsEdit = async (content, section) => {
    try {
      await updateSRSSection(projectId, section, content);
      toast.success(`Applied to "${SECTION_OPTIONS.find((s) => s.value === section)?.label || section}"`);
      onConversationUpdated?.(conversationId, true);
    } catch (e) {
      toast.error("Apply failed", { description: e.response?.data?.detail || e.message });
    }
  };

  return (
    <div className="h-full flex flex-col mos-panel min-h-0">
      {/* Header */}
      <div className="px-4 py-3 border-b border-[#E6E6E6] flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Bot className="w-4 h-4 text-[#2E2E38]" />
          <h3 className="font-display text-sm font-bold tracking-tight">Discovery Chat</h3>
          <HelpIcon text="Conversational gap analysis. The model asks clarifying questions grounded in your KB until enough context is gathered to write the SRS." testId="help-chat" />
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setSrsEditMode((m) => !m)}
            data-testid="srs-edit-mode-btn"
            className={`text-xs px-2 py-1 rounded-sm border flex items-center gap-1 ${
              srsEditMode
                ? "bg-[#FFE600] text-[#2E2E38] border-[#FFE600] font-semibold"
                : "bg-white text-[#747480] border-[#E6E6E6] hover:border-[#2E2E38]"
            }`}
          >
            <Pencil className="w-3 h-3" /> SRS Edit
          </button>
          <label className="text-[10px] uppercase tracking-wider text-[#747480] flex items-center">
            <Cpu className="w-3 h-3 mr-1" />
            Model
            <HelpIcon text="Pick the LLM for this message. DeepSeek Chat is best for SRS; Coder for code analysis; Qwen as fallback." testId="help-model" />
          </label>
          <select
            data-testid="model-selector"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className="bg-white border border-[#E6E6E6] rounded-sm px-2 py-1 text-xs focus:border-[#2E2E38] focus:ring-1 focus:ring-[#2E2E38] outline-none"
          >
            {models.map((m) => (
              <option key={m.id} value={m.id}>{m.label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* SRS Edit Mode strip */}
      {srsEditMode && (
        <div className="px-4 py-2 bg-[#FFE600]/10 border-b border-[#FFE600]/40 flex items-center gap-2" data-testid="srs-edit-strip">
          <span className="text-[10px] uppercase tracking-wider text-[#2E2E38] font-semibold">Editing section:</span>
          <select
            data-testid="srs-edit-section-select"
            value={editSection}
            onChange={(e) => setEditSection(e.target.value)}
            className="text-xs border border-[#E6E6E6] rounded-sm px-2 py-1 bg-white focus:border-[#2E2E38] focus:ring-1 focus:ring-[#2E2E38] outline-none"
          >
            {SECTION_OPTIONS.map((s) => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </select>
          <span className="text-[10px] text-[#747480]">Describe what to add or change.</span>
        </div>
      )}

      {/* Token counter */}
      <div className="px-4 py-1.5 border-b border-[#E6E6E6] bg-[#F6F6FA] flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-wider text-[#747480]">
          Conversation tokens: <span className="font-mono text-[#2E2E38] font-semibold" data-testid="token-counter">{tokens.toLocaleString()}</span>
        </span>
        <span className="text-[10px] text-[#747480]">{kbReady ? "KB Ready" : "Build KB to start"}</span>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto mos-scroll px-4 py-4 space-y-3" data-testid="chat-history">
        {history.length === 0 && (
          <div className="text-center text-[#747480] text-sm py-10">
            <Bot className="w-6 h-6 mx-auto mb-2 text-[#747480]" />
            {kbReady
              ? "Type a message to begin. The model will ground its answers in your knowledge base."
              : "Upload source files and build the knowledge base to start the discovery conversation."}
          </div>
        )}
        {history.map((m, i) => (
          <div key={m.id || i} className={`flex gap-2 ${m.role === "user" ? "flex-row-reverse" : ""}`}>
            <div className={`w-7 h-7 rounded-sm flex items-center justify-center shrink-0 ${m.role === "user" ? "bg-[#2E2E38] text-white" : "bg-[#F6F6FA] text-[#2E2E38] border border-[#E6E6E6]"}`}>
              {m.role === "user" ? <User className="w-3.5 h-3.5" /> : <Bot className="w-3.5 h-3.5" />}
            </div>
            <div className={`max-w-[78%] px-3 py-2 rounded-sm border ${m.role === "user" ? "bg-[#2E2E38] text-white border-[#2E2E38]" : "bg-white border-[#E6E6E6]"}`}>
              <div className="text-[13px] leading-relaxed whitespace-pre-wrap">{m.content}</div>
              {m.model && <div className={`text-[10px] mt-1 ${m.role === "user" ? "text-white/60" : "text-[#747480]"}`}>{m.model} · {m.tokens} tok</div>}
              {m.role === "assistant" && m._editSection && (
                <button
                  type="button"
                  onClick={() => applySrsEdit(m.content, m._editSection)}
                  data-testid={`apply-srs-edit-${i}`}
                  className="text-[10px] bg-[#FFE600] text-[#2E2E38] px-2 py-1 rounded-sm font-semibold mt-2 inline-flex items-center hover:bg-[#FFD700]"
                >
                  <Pencil className="w-2.5 h-2.5 mr-1" /> Apply to SRS
                </button>
              )}
            </div>
          </div>
        ))}
        {sending && (
          <div className="flex gap-2">
            <div className="w-7 h-7 rounded-sm flex items-center justify-center bg-[#F6F6FA] border border-[#E6E6E6]">
              <Bot className="w-3.5 h-3.5" />
            </div>
            <div className="px-3 py-2 rounded-sm border bg-white border-[#E6E6E6] text-[13px] text-[#747480]">Thinking…</div>
          </div>
        )}
      </div>

      {/* Input */}
      <div className="border-t border-[#E6E6E6] p-3 relative">
        {suggestions.length > 0 && (
          <div className="mos-typeahead" data-testid="typeahead">
            {suggestions.map((s) => (
              <button
                key={s}
                onClick={() => { setInput((cur) => cur + " " + s); setSuggestions([]); }}
                className="block w-full text-left px-3 py-1.5 text-xs hover:bg-[#F6F6FA] font-mono"
              >
                {s}
              </button>
            ))}
          </div>
        )}
        <div className="flex items-end gap-2">
          <textarea
            data-testid="chat-input"
            value={input}
            onChange={(e) => onInputChange(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
            placeholder={kbReady ? "Ask a question or describe a requirement…" : "Build KB first…"}
            rows={2}
            disabled={!kbReady || sending}
            className="flex-1 bg-white border border-[#E6E6E6] rounded-sm px-3 py-2 text-sm resize-none focus:border-[#2E2E38] focus:ring-1 focus:ring-[#2E2E38] outline-none disabled:bg-slate-50 disabled:text-slate-400"
          />
          <button
            data-testid="send-btn"
            onClick={send}
            disabled={!kbReady || sending || !input.trim()}
            className="bg-[#2E2E38] text-white hover:bg-[#1A1A24] disabled:bg-slate-300 rounded-sm px-3 py-2 font-semibold flex items-center"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
        <div className="text-[10px] text-slate-400 mt-1.5">
          Enter to send · Shift+Enter for newline · Type to see KB term suggestions
        </div>
      </div>
    </div>
  );
}
