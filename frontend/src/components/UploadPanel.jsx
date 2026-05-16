import React, { useEffect, useState, useCallback, useRef } from "react";
import { Upload, FileText, Trash2, Hammer, Database, Boxes, Users, GitBranch } from "lucide-react";
import { uploadKBFiles, listKBFiles, deleteKBFile, buildKB, kbStatus } from "@/lib/api";
import HelpIcon from "@/components/HelpIcon";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

const ACCEPT = ".php,.sql,.pdf,.csv,.docx,.txt,.md";

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
      <div className="font-display text-2xl font-bold mt-1 text-[#0A2540]">{value ?? 0}</div>
    </div>
  );
}

export default function UploadPanel({ projectId, onKBUpdated }) {
  const [files, setFiles] = useState([]);
  const [status, setStatus] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [building, setBuilding] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef(null);

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

  const handleDelete = async (id) => {
    await deleteKBFile(id);
    toast.success("File deleted");
    await refresh();
  };

  return (
    <div className="h-full flex flex-col gap-4 overflow-hidden">
      {/* Dropzone */}
      <div className="mos-panel p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-display text-sm font-bold tracking-tight flex items-center">
            Source Files
            <HelpIcon text="Upload legacy code (.php, .sql), docs (.pdf, .docx), or data (.csv). MigrationOS chunks them and extracts an ontology." testId="help-upload" />
          </h3>
          <span className="text-[10px] text-slate-500 uppercase tracking-wider">{files.length} files</span>
        </div>
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
          className={`border-2 border-dashed rounded-sm py-6 px-4 text-center cursor-pointer ${
            dragOver ? "border-[#0A2540] bg-slate-50" : "border-slate-300 hover:border-slate-400"
          }`}
        >
          <Upload className="w-5 h-5 mx-auto text-slate-500 mb-2" />
          <div className="text-sm text-slate-700 font-medium">{uploading ? "Uploading…" : "Drop files or click to browse"}</div>
          <div className="text-[11px] text-slate-500 mt-1">Accepts: .php, .sql, .pdf, .docx, .csv, .txt</div>
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
        <div className="px-4 py-2.5 border-b border-slate-200 mos-label">Uploaded</div>
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
        <div className="px-4 py-3 border-t border-slate-200">
          <Button
            data-testid="build-kb-btn"
            disabled={files.length === 0 || building}
            onClick={handleBuild}
            className="w-full bg-[#0A2540] text-white hover:bg-[#021122] rounded-sm font-semibold"
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
          <HelpIcon text="After Build, MigrationOS extracts classes, methods, tables, columns, FKs, roles, and routes from your sources." testId="help-kbhealth" />
        </div>
        <div className="grid grid-cols-2 gap-2">
          <MetricCard icon={Boxes} label="Entities" value={status?.entities} testId="metric-entities" help="Total ontology entities (classes + tables + routes + individuals)." />
          <MetricCard icon={Database} label="Tables" value={status?.tables} testId="metric-tables" help="Distinct database tables detected from SQL DDL." />
          <MetricCard icon={GitBranch} label="Relations" value={status?.relationships} testId="metric-relations" help="Foreign-key relationships between tables." />
          <MetricCard icon={Users} label="Roles" value={status?.roles} testId="metric-roles" help="Roles extracted from INSERT statements into role-like tables." />
        </div>
      </div>
    </div>
  );
}
