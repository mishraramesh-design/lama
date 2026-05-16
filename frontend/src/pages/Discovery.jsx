import React, { useState } from "react";
import { useProjects } from "@/state/ProjectContext";
import UploadPanel from "@/components/UploadPanel";
import ChatPanel from "@/components/ChatPanel";
import SRSPanel from "@/components/SRSPanel";

export default function DiscoveryPage() {
  const { active } = useProjects();
  const [kbStatus, setKbStatus] = useState(null);
  const [conversationId, setConversationId] = useState(null);

  const kbReady = (kbStatus?.entities || 0) > 0;

  if (!active) {
    return (
      <div className="flex-1 flex items-center justify-center text-slate-500" data-testid="no-project">
        <div className="text-center">
          <div className="text-base font-display font-semibold mb-1">No project selected</div>
          <div className="text-sm">Create or pick a project in the sidebar.</div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col min-w-0">
      {/* Stage header */}
      <header className="bg-white border-b border-slate-300 px-6 py-3 flex items-center justify-between">
        <div>
          <div className="text-[10px] uppercase tracking-widest text-slate-500">Stage 1 of 5</div>
          <h1 className="font-display text-lg font-bold tracking-tight text-[#0A2540]">Discovery & SRS</h1>
        </div>
        <div className="text-right">
          <div className="text-[10px] uppercase tracking-widest text-slate-500">Project</div>
          <div className="text-sm font-semibold text-slate-800">{active.name}</div>
        </div>
      </header>

      {/* 3-panel grid */}
      <div className="flex-1 grid grid-cols-12 gap-4 p-4 min-h-0 bg-slate-100">
        <div className="col-span-3 min-h-0 overflow-hidden" data-testid="panel-upload">
          <UploadPanel projectId={active.id} onKBUpdated={setKbStatus} />
        </div>
        <div className="col-span-5 min-h-0" data-testid="panel-chat">
          <ChatPanel projectId={active.id} kbReady={kbReady} onConversationUpdated={setConversationId} />
        </div>
        <div className="col-span-4 min-h-0" data-testid="panel-srs">
          <SRSPanel projectId={active.id} conversationId={conversationId} kbReady={kbReady} />
        </div>
      </div>
    </div>
  );
}
