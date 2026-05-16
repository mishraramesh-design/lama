import React, { useEffect, useState, useRef, useCallback } from "react";
import { Send, Bot, User, Cpu } from "lucide-react";
import { chatHistory, sendMessage, listModels, kbGlossary } from "@/lib/api";
import HelpIcon from "@/components/HelpIcon";
import { toast } from "sonner";

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
      });
      setConversationId(r.conversation_id);
      setHistory((h) => [...h, r.message]);
      setTokens((t) => t + (r.usage?.total_tokens || 0));
      onConversationUpdated?.(r.conversation_id, r.srs_triggered);
    } catch (e) {
      toast.error("Chat failed", { description: e.response?.data?.detail || e.message });
      setHistory((h) => h.slice(0, -1));
      setInput(text);
    } finally {
      setSending(false);
    }
  }, [input, sending, projectId, model, conversationId, onConversationUpdated]);

  return (
    <div className="h-full flex flex-col mos-panel min-h-0">
      {/* Header */}
      <div className="px-4 py-3 border-b border-slate-200 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Bot className="w-4 h-4 text-[#0A2540]" />
          <h3 className="font-display text-sm font-bold tracking-tight">Discovery Chat</h3>
          <HelpIcon text="Conversational gap analysis. The model asks clarifying questions grounded in your KB until enough context is gathered to write the SRS." testId="help-chat" />
        </div>
        <div className="flex items-center gap-2">
          <label className="text-[10px] uppercase tracking-wider text-slate-500 flex items-center">
            <Cpu className="w-3 h-3 mr-1" />
            Model
            <HelpIcon text="Pick the LLM for this message. DeepSeek Chat is best for SRS; Coder for code analysis; Qwen as fallback." testId="help-model" />
          </label>
          <select
            data-testid="model-selector"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className="bg-white border border-slate-300 rounded-sm px-2 py-1 text-xs focus:border-[#0A2540] focus:ring-1 focus:ring-[#0A2540] outline-none"
          >
            {models.map((m) => (
              <option key={m.id} value={m.id}>{m.label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Token counter */}
      <div className="px-4 py-1.5 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-wider text-slate-500">
          Conversation tokens: <span className="font-mono text-slate-800 font-semibold" data-testid="token-counter">{tokens.toLocaleString()}</span>
        </span>
        <span className="text-[10px] text-slate-500">{kbReady ? "KB Ready" : "Build KB to start"}</span>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto mos-scroll px-4 py-4 space-y-3" data-testid="chat-history">
        {history.length === 0 && (
          <div className="text-center text-slate-500 text-sm py-10">
            <Bot className="w-6 h-6 mx-auto mb-2 text-slate-400" />
            {kbReady
              ? "Type a message to begin. The model will ground its answers in your knowledge base."
              : "Upload source files and build the knowledge base to start the discovery conversation."}
          </div>
        )}
        {history.map((m, i) => (
          <div key={m.id || i} className={`flex gap-2 ${m.role === "user" ? "flex-row-reverse" : ""}`}>
            <div className={`w-7 h-7 rounded-sm flex items-center justify-center shrink-0 ${m.role === "user" ? "bg-[#0A2540] text-white" : "bg-slate-200 text-slate-700"}`}>
              {m.role === "user" ? <User className="w-3.5 h-3.5" /> : <Bot className="w-3.5 h-3.5" />}
            </div>
            <div className={`max-w-[78%] px-3 py-2 rounded-sm border ${m.role === "user" ? "bg-[#0A2540] text-white border-[#0A2540]" : "bg-white border-slate-200"}`}>
              <div className="text-[13px] leading-relaxed whitespace-pre-wrap">{m.content}</div>
              {m.model && <div className={`text-[10px] mt-1 ${m.role === "user" ? "text-white/60" : "text-slate-400"}`}>{m.model} · {m.tokens} tok</div>}
            </div>
          </div>
        ))}
        {sending && (
          <div className="flex gap-2">
            <div className="w-7 h-7 rounded-sm flex items-center justify-center bg-slate-200">
              <Bot className="w-3.5 h-3.5" />
            </div>
            <div className="px-3 py-2 rounded-sm border bg-white border-slate-200 text-[13px] text-slate-500">Thinking…</div>
          </div>
        )}
      </div>

      {/* Input */}
      <div className="border-t border-slate-200 p-3 relative">
        {suggestions.length > 0 && (
          <div className="mos-typeahead" data-testid="typeahead">
            {suggestions.map((s) => (
              <button
                key={s}
                onClick={() => { setInput((cur) => cur + " " + s); setSuggestions([]); }}
                className="block w-full text-left px-3 py-1.5 text-xs hover:bg-slate-100 font-mono"
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
            className="flex-1 bg-white border border-slate-300 rounded-sm px-3 py-2 text-sm resize-none focus:border-[#0A2540] focus:ring-1 focus:ring-[#0A2540] outline-none disabled:bg-slate-50 disabled:text-slate-400"
          />
          <button
            data-testid="send-btn"
            onClick={send}
            disabled={!kbReady || sending || !input.trim()}
            className="bg-[#0A2540] text-white hover:bg-[#021122] disabled:bg-slate-300 rounded-sm px-3 py-2 font-semibold flex items-center"
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
