import React, { useEffect, useState, useCallback, useRef } from "react";
import { Upload, FileText, Trash2, Hammer, Database, Boxes, Users, GitBranch, FolderSearch, ChevronLeft, Download, TableProperties, ChevronUp, ChevronDown, Loader2 } from "lucide-react";
import { uploadKBFiles, listKBFiles, deleteKBFile, buildKB, kbStatus, scanFolder, owlExportUrl, importModuleInventory, getModuleTraceability } from "@/lib/api";
import HelpIcon from "@/components/HelpIcon";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

const ACCEPT = ".php,.sql,.pdf,.csv,.docx,.txt,.md,.zip";

function MetricCard({ icon: Icon, label, value, testId, help }) {
  return (
    <div data-testid={testId} className="mos-panel p-3">
      <div className="flex items-center justify-between text-slate-500">
        <div className="flex items-center gap-1.5">
          <Icon className="w-3.5 h-3.5" />
          <span className="text-[10px] font-semibold uppercase tracking-wider">{label}</span>
        </div>
        {help && <HelpIcon text={help} testId={`help-${testId}`} />}
      </div>
      <div className="font-display text-2xl font-bold mt-1 text-[#2E2E38]">{value ?? 0}</div>
    </div>
  );
}

export default function UploadPanel({ projectId, onKBUpdated, onCollapse }) {
  const [files, setFiles] = useState([]);
  const [status, setStatus] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [building, setBuilding] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [folderPath, setFolderPath] = useState("");
  const [scanning, setScanning] = useState(false);
  const inputRef = useRef(null);
  const moduleInputRef = useRef(null);
  const [moduleFile, setModuleFile] = useState(null);
  const [moduleImporting, setModuleImporting] = useState(false);
  const [moduleImportResult, setModuleImportResult] = useState("");
  const [showTraceability, setShowTraceability] = useState(false);
  const [traceData, setTraceData] = useState(null);
  const [traceView, setTraceView] = useState("user");

  const refresh = useCallback(async () => {
    if (!projectId) return;
    const [fls, st] = await Promise.all([listKBFiles(projectId), kbStatus(projectId)]);
    setFiles(fls);
    setStatus(st);
    onKBUpdated?.(st);
  }, [projectId, onKBUpdated]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleUpload = async (fileList) => {
    if (!projectId || !fileList?.length) return;
    setUploading(true);
    try {
      await uploadKBFiles(projectId, Array.from(fileList));
      toast.success(`${fileList.length} file(s) uploaded`);
      await refresh();
    } catch (e) {
      toast.error("Upload failed", { description: e.response?.data?.detail || e.message });
    } finally {
      setUploading(false);
    }
  };

  const handleBuild = async () => {
    if (!projectId) return;
    setBuilding(true);
    try {
      const r = await buildKB(projectId);
      toast.success("Knowledge Base built", { description: r.summary });
      await refresh();
    } catch (e) {
      toast.error("Build failed", { description: e.response?.data?.detail || e.message });
    } finally {
      setBuilding(false);
    }
  };

  const handleScanFolder = async () => {
    if (!folderPath.trim()) {
      toast.error("Enter a folder path");
      return;
    }
    setScanning(true);
    try {
      const r = await scanFolder(projectId, folderPath.trim());
      toast.success(`Scanned ${r.scanned} file(s)`, { description: r.skipped ? `${r.skipped} skipped` : undefined });
      await refresh();
    } catch (e) {
      toast.error("Scan failed", { description: e.response?.data?.detail || e.message });
    } finally {
      setScanning(false);
    }
  };

  const handleDelete = async (id) => {
    await deleteKBFile(id);
    toast.success("File deleted");
    await refresh();
  };

  const handleModuleImport = async () => {
    if (!moduleFile || !projectId) return;
    setModuleImporting(true);
    setModuleImportResult("");
    try {
      const r = await importModuleInventory(projectId, moduleFile);
      setModuleImportResult(r.message || "Imported.");
      setModuleFile(null);
      if (moduleInputRef.current) moduleInputRef.current.value = "";
      setTraceData(null);
      await refresh();
      toast.success("Module inventory imported", { description: r.message });
    } catch (e) {
      toast.error("Import failed", { description: e.response?.data?.detail || e.message });
    } finally {
      setModuleImporting(false);
    }
  };

  const toggleTraceability = () => {
    const next = !showTraceability;
    setShowTraceability(next);
    if (next && !traceData && projectId) {
      getModuleTraceability(projectId)
        .then(setTraceData)
        .catch(() => toast.error("Could not load traceability"));
    }
  };

  return (
    <div className="h-full flex flex-col gap-4 overflow-hidden">
      {/* Source ingest */}
      <div className="mos-panel p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-display text-sm font-bold tracking-tight flex items-center">
            Source Files
            <HelpIcon text="Ingest legacy code by entering the absolute folder path on the server (recommended for large codebases) or by drag-dropping individual files." testId="help-upload" />
          </h3>
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-[#747480] uppercase tracking-wider">{files.length} files</span>
            {onCollapse && (
              <button
                type="button"
                onClick={onCollapse}
                data-testid="collapse-upload"
                className="text-[#747480] hover:text-[#2E2E38] p-0.5"
                aria-label="Collapse panel"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>

        {/* Mode A — Folder path */}
        <div className="mb-3">
          <label className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold flex items-center mb-1">
            <FolderSearch className="w-3 h-3 mr-1" />
            Legacy codebase folder path
            <HelpIcon text="Enter the absolute path to your legacy application folder on the server. LAMA will scan all .php, .sql, .pdf, .csv, .docx, .txt, .md files recursively. node_modules, .git, vendor, backups (*.bak, *.save, *_bkp, *.php_*) are skipped." testId="help-folder-path" />
          </label>
          <div className="flex gap-2">
            <Input
              data-testid="folder-path-input"
              value={folderPath}
              onChange={(e) => setFolderPath(e.target.value)}
              placeholder="/home/user/projects/pmis  or  C:\projects\pmis"
              className="flex-1 rounded-sm font-mono text-xs"
            />
            <Button
              data-testid="scan-folder-btn"
              onClick={handleScanFolder}
              disabled={scanning || !folderPath.trim()}
              className="bg-[#2E2E38] text-white hover:bg-[#1A1A24] rounded-sm text-xs h-9 px-3 whitespace-nowrap"
            >
              {scanning ? "Scanning…" : "Scan Folder"}
            </Button>
          </div>
        </div>

        {/* Mode B — Individual file upload */}
        <div className="mos-label mb-1.5">Or upload individual files</div>
        <div
          data-testid="dropzone"
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            handleUpload(e.dataTransfer.files);
          }}
          className={`border-2 border-dashed rounded-sm py-4 px-4 text-center cursor-pointer ${
            dragOver ? "border-[#2E2E38] bg-slate-50" : "border-[#E6E6E6] hover:border-slate-400"
          }`}
        >
          <Upload className="w-4 h-4 mx-auto text-slate-500 mb-1" />
          <div className="text-xs text-slate-700 font-medium">{uploading ? "Uploading…" : "Drop files or click to browse"}</div>
          <div className="text-[10px] text-slate-500 mt-0.5">.php · .sql · .pdf · .docx · .csv · .txt · .zip</div>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept={ACCEPT}
            className="hidden"
            data-testid="file-input"
            onChange={(e) => handleUpload(e.target.files)}
          />
        </div>
      </div>

      {/* File list */}
      <div className="mos-panel flex-1 flex flex-col min-h-0">
        <div className="px-4 py-2.5 border-b border-[#E6E6E6] mos-label">Uploaded</div>
        <div className="flex-1 overflow-y-auto mos-scroll">
          {files.length === 0 ? (
            <div className="p-4 text-xs text-slate-500">No files yet.</div>
          ) : (
            <ul className="divide-y divide-slate-200">
              {files.map((f) => (
                <li key={f.id} className="px-4 py-2.5 flex items-center gap-2" data-testid={`file-${f.filename}`}>
                  <FileText className="w-4 h-4 text-slate-500 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-slate-800 truncate">{f.filename}</div>
                    <div className="text-[10px] text-slate-500 uppercase tracking-wider">
                      {f.filetype} · {f.chunk_count} chunks · {f.entity_count} entities · {f.status}
                    </div>
                  </div>
                  <button
                    onClick={() => handleDelete(f.id)}
                    className="text-slate-400 hover:text-red-600"
                    data-testid={`delete-${f.filename}`}
                    aria-label="Delete file"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="px-4 pb-3 border-t border-[#E6E6E6] pt-3">
          <div className="mos-label mb-2 flex items-center">
            <TableProperties className="w-3 h-3 mr-1" />
            Module Inventory
            <HelpIcon text="Optional: upload a pre-analysed Excel / CSV / JSON file mapping legacy modules to their components and DB tables. LAMA fuzzy-matches columns so any naming convention works." testId="help-module-inv" />
          </div>
          <label
            htmlFor="module-inventory-input"
            className="block border-2 border-dashed border-[#E6E6E6] rounded-sm p-3 text-center text-[11px] text-[#747480] cursor-pointer hover:border-[#2E2E38]"
            data-testid="module-inventory-dropzone"
          >
            {moduleFile ? <span className="text-[#2E2E38] font-mono">{moduleFile.name}</span> : "Drop .xlsx / .csv / .json"}
            <input
              ref={moduleInputRef}
              id="module-inventory-input"
              type="file"
              accept=".xlsx,.xls,.csv,.json"
              className="hidden"
              data-testid="module-inventory-input"
              onChange={(e) => setModuleFile(e.target.files?.[0] || null)}
            />
          </label>
          {moduleFile && (
            <Button
              size="sm"
              data-testid="module-inventory-import-btn"
              onClick={handleModuleImport}
              disabled={moduleImporting}
              className="w-full mt-2 bg-[#2E2E38] text-white hover:bg-[#1A1A24] rounded-sm text-xs h-8"
            >
              {moduleImporting ? (
                <>
                  <Loader2 className="w-3 h-3 mr-1 animate-spin" /> Importing…
                </>
              ) : (
                <>
                  <Upload className="w-3 h-3 mr-1" /> Import Module Inventory
                </>
              )}
            </Button>
          )}
          {moduleImportResult && (
            <div className="text-[10px] text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-sm px-2 py-1 mt-2" data-testid="module-import-result">
              ✓ {moduleImportResult}
            </div>
          )}
        </div>
        <div className="px-4 py-3 border-t border-[#E6E6E6]">
          <Button
            data-testid="build-kb-btn"
            disabled={files.length === 0 || building}
            onClick={handleBuild}
            className="w-full bg-[#2E2E38] text-white hover:bg-[#1A1A24] rounded-sm font-semibold"
          >
            <Hammer className="w-4 h-4 mr-2" />
            {building ? "Building…" : "Build Knowledge Base"}
          </Button>
        </div>
      </div>

      {/* KB Health */}
      <div className="mos-panel p-4">
        <div className="mos-label mb-2 flex items-center">
          KB Health
          <HelpIcon text="After Build, LAMA extracts classes, methods, tables, columns, FKs, roles, and routes from your sources." testId="help-kbhealth" />
        </div>
        <div className="grid grid-cols-2 gap-2">
          <MetricCard icon={Boxes} label="Entities" value={status?.entities} testId="metric-entities" help="Total ontology entities (classes + tables + routes + individuals)." />
          <MetricCard icon={Database} label="Tables" value={status?.tables} testId="metric-tables" help="Distinct database tables detected from SQL DDL." />
          <MetricCard icon={GitBranch} label="Relations" value={status?.relationships} testId="metric-relations" help="Foreign-key relationships between tables." />
          <MetricCard icon={Users} label="Roles" value={status?.roles} testId="metric-roles" help="Roles extracted from INSERT statements into role-like tables." />
          {(status?.modules || 0) > 0 && (
            <MetricCard icon={TableProperties} label="Modules" value={status?.modules} testId="metric-modules" help="Business modules imported from your Module Inventory file." />
          )}
        </div>
        <button
          data-testid="owl-export-btn"
          onClick={() => window.open(owlExportUrl(projectId), "_blank")}
          disabled={!status?.entities}
          className="flex items-center gap-1.5 text-xs border border-[#E6E6E6] rounded-sm px-2 py-1.5 bg-white hover:border-[#2E2E38] disabled:opacity-40 disabled:cursor-not-allowed mt-2 w-full justify-center"
          title="Downloads OWL/JSON-LD ontology used by Stage 2 and Stage 3"
        >
          <Download className="w-3.5 h-3.5" /> Download OWL Context
        </button>
      </div>

      {/* Module Traceability */}
      <div className="mos-panel p-4" data-testid="module-traceability-card">
        <div className="flex items-center justify-between cursor-pointer" onClick={toggleTraceability}>
          <div className="mos-label flex items-center">
            <GitBranch className="w-3 h-3 mr-1" />
            Module Traceability
          </div>
          <button
            type="button"
            aria-label="toggle"
            data-testid="toggle-traceability"
            className="text-[#747480] hover:text-[#2E2E38]"
          >
            {showTraceability ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          </button>
        </div>
        {showTraceability && !traceData && (
          <div className="text-[10px] text-[#747480] mt-2" data-testid="traceability-loading">Loading…</div>
        )}
        {showTraceability && traceData && (
          <div className="mt-2 space-y-2" data-testid="traceability-body">
            <div className="flex gap-1">
              {[
                ["user", `Imported (${(traceData.user_modules || []).length})`],
                ["auto", `Auto-detected (${(traceData.auto_modules || []).length})`],
              ].map(([v, label]) => (
                <button
                  key={v}
                  type="button"
                  onClick={() => setTraceView(v)}
                  data-testid={`trace-view-${v}`}
                  className={`text-[10px] px-2 py-0.5 rounded-sm border ${
                    traceView === v
                      ? "bg-[#2E2E38] text-white border-[#2E2E38]"
                      : "bg-white text-[#747480] border-[#E6E6E6]"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            {traceView === "user" && (
              <div className="space-y-1 max-h-48 overflow-y-auto mos-scroll" data-testid="trace-user-list">
                {!traceData.has_user_import && (
                  <div className="text-[10px] text-[#747480] italic text-center py-3">No module inventory imported yet.</div>
                )}
                {(traceData.user_modules || []).map((m) => (
                  <div key={m.name} className="border border-[#E6E6E6] rounded-sm p-1.5 bg-white">
                    <div className="flex items-center justify-between gap-1">
                      <div className="text-[11px] font-semibold text-[#2E2E38] truncate">{m.name}</div>
                      <span className="text-[9px] text-[#747480] shrink-0">
                        {m.component_count}c · {m.table_ref_count}t
                      </span>
                    </div>
                    {m.description && (
                      <div className="text-[10px] text-[#747480] line-clamp-2">{m.description}</div>
                    )}
                    <div className="text-[10px] text-[#747480] font-mono mt-0.5 truncate">
                      {(m.tables || []).slice(0, 4).join(", ")}
                      {(m.tables || []).length > 4 && ` +${m.tables.length - 4}`}
                    </div>
                  </div>
                ))}
              </div>
            )}
            {traceView === "auto" && (
              <div className="space-y-1 max-h-48 overflow-y-auto mos-scroll" data-testid="trace-auto-list">
                {(traceData.auto_modules || []).map((d) => (
                  <div key={d.domain} className="border border-[#E6E6E6] rounded-sm p-1.5 bg-white">
                    <div className="flex items-center justify-between gap-1">
                      <div className="text-[11px] font-semibold text-[#2E2E38] truncate">{d.domain}</div>
                      <span className="text-[9px] text-[#747480] shrink-0">
                        {d.class_count}c · {d.table_count}t
                      </span>
                    </div>
                    <div className="text-[10px] text-[#747480] font-mono mt-0.5 truncate">
                      {(d.sample_tables || []).slice(0, 3).join(", ")}
                      {d.table_count > 3 && ` +${d.table_count - 3} more`}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
