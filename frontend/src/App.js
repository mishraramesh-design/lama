import React from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";
import { ProjectProvider } from "@/state/ProjectContext";
import Sidebar from "@/components/Sidebar";
import DiscoveryPage from "@/pages/Discovery";
import DataModelPage from "@/pages/DataModel";
import PromptLibraryPage from "@/pages/PromptLibrary";
import AuditLogPage from "@/pages/AuditLog";
import GitHubSettingsPage from "@/pages/GitHubSettings";

function Shell({ children }) {
  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <Sidebar />
      {children}
    </div>
  );
}

function App() {
  return (
    <ProjectProvider>
      <BrowserRouter>
        <Toaster position="top-right" />
        <Routes>
          <Route path="/" element={<Shell><DiscoveryPage /></Shell>} />
          <Route path="/data-model" element={<Shell><DataModelPage /></Shell>} />
          <Route path="/prompts" element={<Shell><PromptLibraryPage /></Shell>} />
          <Route path="/settings" element={<Shell><GitHubSettingsPage /></Shell>} />
          <Route path="/audit" element={<Shell><AuditLogPage /></Shell>} />
        </Routes>
      </BrowserRouter>
    </ProjectProvider>
  );
}

export default App;
