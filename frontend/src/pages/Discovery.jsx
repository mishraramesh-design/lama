import React, { useState } from "react";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useProjects } from "@/state/ProjectContext";
import UploadPanel from "@/components/UploadPanel";
import ChatPanel from "@/components/ChatPanel";
import SRSPanel from "@/components/SRSPanel";

export default function DiscoveryPage() {
  const { active } = useProjects();
  const [kbStatus, setKbStatus] = useState(null);
  const [conversationId, setConversationId] = useState(null);
  const [srsRefreshKey, setSrsRefreshKey] = useState(0);

  const [uploadCollapsed, setUploadCollapsed] = useState(
    typeof window !== "undefined" && localStorage.getItem("lama:panel:upload") === "true"
  );
  const [srsCollapsed, setSrsCollapsed] = useState(
    typeof window !== "undefined" && localStorage.getItem("lama:panel:srs") === "true"
  );

  const kbReady = (kbStatus?.entities || 0) > 0;

  const toggle = (key) => {
    if (key === "upload") {
      const v = !uploadCollapsed;
      localStorage.setItem("lama:panel:upload", String(v));
      setUploadCollapsed(v);
    } else {
      const v = !srsCollapsed;
      localStorage.setItem("lama:panel:srs", String(v));
      setSrsCollapsed(v);
    }
  };

  const handleConversationUpdated = (cid, srsTriggered) => {
    setConversationId(cid);
    if (srsTriggered) setSrsRefreshKey((k) => k + 1);
  };

  if (!active) {
    return (
      <div className="flex-1 flex items-center justify-center text-[#747480]" data-testid="no-project">
        <div className="text-center">
          <div className="text-base font-display font-semibold mb-1">No project selected</div>
          <div className="text-sm">Create or pick a project in the sidebar.</div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col min-w-0">
      {/* Stage header with EY yellow accent line */}
      <header className="bg-white border-b-2 border-[#FFE600] px-6 py-3 flex items-center justify-between">
        <div>
          <div className="text-[10px] uppercase tracking-widest text-[#747480]">Stage 1 of 5</div>
          <h1 className="font-display text-lg font-bold tracking-tight text-[#2E2E38]">Discovery &amp; SRS</h1>
        </div>
        <div className="text-right">
          <div className="text-[10px] uppercase tracking-widest text-[#747480]">Project</div>
          <div className="text-sm font-semibold text-[#2E2E38]">{active.name}</div>
        </div>
      </header>

      {/* Resizable 3-panel layout */}
      <PanelGroup direction="horizontal" className="flex-1 min-h-0 bg-[#F6F6FA]" autoSaveId="lama-discovery">
        {!uploadCollapsed ? (
          <>
            <Panel defaultSize={25} minSize={15} maxSize={40} id="upload" order={1}>
              <div className="h-full p-2" data-testid="panel-upload">
                <UploadPanel
                  projectId={active.id}
                  onKBUpdated={setKbStatus}
                  onCollapse={() => toggle("upload")}
                />
              </div>
            </Panel>
            <PanelResizeHandle className="lama-resize-handle" />
          </>
        ) : (
          <div
            className="w-8 flex flex-col items-center bg-white border-r border-[#E6E6E6] py-3 gap-2 cursor-pointer hover:bg-[#F6F6FA]"
            onClick={() => toggle("upload")}
            data-testid="expand-upload"
          >
            <ChevronRight className="w-4 h-4 text-[#747480]" />
            <span className="text-[10px] text-[#747480] uppercase tracking-widest" style={{ writingMode: "vertical-rl" }}>KB</span>
          </div>
        )}

        <Panel
          defaultSize={uploadCollapsed && srsCollapsed ? 100 : uploadCollapsed || srsCollapsed ? 65 : 42}
          minSize={25}
          id="chat"
          order={2}
        >
          <div className="h-full p-2" data-testid="panel-chat">
            <ChatPanel projectId={active.id} kbReady={kbReady} onConversationUpdated={handleConversationUpdated} />
          </div>
        </Panel>

        {!srsCollapsed ? (
          <>
            <PanelResizeHandle className="lama-resize-handle" />
            <Panel defaultSize={33} minSize={20} id="srs" order={3}>
              <div className="h-full p-2" data-testid="panel-srs">
                <SRSPanel
                  key={srsRefreshKey}
                  projectId={active.id}
                  conversationId={conversationId}
                  kbReady={kbReady}
                  onCollapse={() => toggle("srs")}
                />
              </div>
            </Panel>
          </>
        ) : (
          <div
            className="w-8 flex flex-col items-center bg-white border-l border-[#E6E6E6] py-3 gap-2 cursor-pointer hover:bg-[#F6F6FA]"
            onClick={() => toggle("srs")}
            data-testid="expand-srs"
          >
            <ChevronLeft className="w-4 h-4 text-[#747480]" />
            <span className="text-[10px] text-[#747480] uppercase tracking-widest" style={{ writingMode: "vertical-rl" }}>SRS</span>
          </div>
        )}
      </PanelGroup>
    </div>
  );
}
