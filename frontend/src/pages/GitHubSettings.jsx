import React, { useEffect, useState } from "react";
import { Github, Folder, Lock, CheckCircle2, XCircle, Cloud } from "lucide-react";
import { useProjects } from "@/state/ProjectContext";
import HelpIcon from "@/components/HelpIcon";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import api from "@/lib/api";
import { toast } from "sonner";

const FOLDER_TREE = `pmis-modernized/
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI route files per domain
│   │   ├── models/       # Pydantic models
│   │   ├── services/     # Business logic
│   │   └── db/           # Database layer
│   ├── migrations/       # Alembic PostgreSQL migrations
│   ├── tests/            # pytest unit tests
│   └── main.py
├── frontend/             # React app
├── schema/               # PostgreSQL DDL files
├── docs/                 # Generated SRS PDF / SRS.md
├── Dockerfile
├── docker-compose.yml
└── README.md`;

export default function GitHubSettingsPage() {
  const { active } = useProjects();
  const [form, setForm] = useState({ repo_url: "", token: "", branch: "main" });
  const [saved, setSaved] = useState(false);
  const [hasToken, setHasToken] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [saving, setSaving] = useState(false);
  const [pushing, setPushing] = useState(false);

  useEffect(() => {
    if (!active?.id) return;
    api.get(`/github/config/${active.id}`).then((r) => {
      setForm((f) => ({ ...f, repo_url: r.data.repo_url || "", branch: r.data.branch || "main" }));
      setHasToken(!!r.data.has_token);
      setSaved(!!r.data.repo_url);
    });
  }, [active?.id]);

  if (!active) {
    return (
      <div className="flex-1 flex items-center justify-center text-slate-500">
        <div className="text-sm">No active project.</div>
      </div>
    );
  }

  const handleSave = async () => {
    if (!form.repo_url || !form.token) {
      toast.error("Repo URL and token are both required");
      return;
    }
    setSaving(true);
    try {
      await api.post("/github/config", { project_id: active.id, ...form });
      toast.success("GitHub config saved");
      setSaved(true);
      setHasToken(true);
    } catch (e) {
      toast.error("Save failed", { description: e.response?.data?.detail || e.message });
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    if (!form.repo_url || !form.token) {
      toast.error("Repo URL and token are both required for test");
      return;
    }
    setTesting(true);
    setTestResult(null);
    try {
      const r = await api.post("/github/test", { repo_url: form.repo_url, token: form.token });
      setTestResult(r.data);
      if (r.data.ok) toast.success(`Connected to ${r.data.repo_name}`);
      else toast.error("Connection failed", { description: r.data.error });
    } catch (e) {
      toast.error("Test failed", { description: e.message });
    } finally {
      setTesting(false);
    }
  };

  const handlePushSRS = async () => {
    setPushing(true);
    try {
      const r = await api.post("/github/push", {
        project_id: active.id,
        repo_url: form.repo_url,
        token: form.token,
        branch: form.branch,
      });
      if (r.data.status === "success") {
        toast.success("SRS pushed", { description: r.data.message });
      } else {
        toast.error("Push failed", { description: r.data.message });
      }
    } catch (e) {
      toast.error("Push failed", { description: e.message });
    } finally {
      setPushing(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col min-w-0">
      <header className="bg-white border-b border-slate-300 px-6 py-3">
        <div className="text-[10px] uppercase tracking-widest text-slate-500">Settings</div>
        <h1 className="font-display text-lg font-bold tracking-tight text-[#0A2540] flex items-center">
          <Github className="w-5 h-5 mr-2" />
          GitHub Configuration
          <HelpIcon text="Connect a GitHub repository so LAMA can push the SRS, schema, and generated code as you progress through stages." testId="help-github-page" />
        </h1>
      </header>

      <div className="flex-1 overflow-y-auto mos-scroll p-6 bg-slate-100">
        <div className="max-w-3xl mx-auto space-y-6">
          {/* Section A — GitHub Config */}
          <section className="mos-panel p-6" data-testid="section-github-config">
            <h2 className="font-display text-sm font-bold tracking-tight text-[#0A2540] mb-1">Repository Connection</h2>
            <p className="text-xs text-slate-500 mb-4">Saved per project. Token is kept on the server.</p>

            <div className="space-y-4">
              <div>
                <Label htmlFor="gh-repo" className="flex items-center text-xs font-semibold uppercase tracking-wider text-slate-600">
                  GitHub Repository
                  <HelpIcon text="The target GitHub repository where LAMA will push generated code, schema files, and Dockerfile. Must exist before pushing." testId="help-gh-repo" />
                </Label>
                <Input
                  id="gh-repo"
                  data-testid="gh-repo"
                  placeholder="https://github.com/org/pmis-modernized"
                  value={form.repo_url}
                  onChange={(e) => setForm({ ...form, repo_url: e.target.value })}
                  className="mt-1 rounded-sm"
                />
              </div>

              <div>
                <Label htmlFor="gh-token" className="flex items-center text-xs font-semibold uppercase tracking-wider text-slate-600">
                  <Lock className="w-3 h-3 mr-1" />
                  Personal Access Token
                  <HelpIcon text="GitHub PAT with repo write permission. Never stored in logs. Kept in session only." testId="help-gh-token" />
                </Label>
                <Input
                  id="gh-token"
                  data-testid="gh-token"
                  type="password"
                  placeholder={hasToken ? "Token saved — enter again to replace" : "ghp_… or github_pat_…"}
                  value={form.token}
                  onChange={(e) => setForm({ ...form, token: e.target.value })}
                  className="mt-1 rounded-sm font-mono text-xs"
                />
              </div>

              <div>
                <Label htmlFor="gh-branch" className="flex items-center text-xs font-semibold uppercase tracking-wider text-slate-600">
                  Target Branch
                  <HelpIcon text="Default branch where LAMA commits. Usually 'main'." testId="help-gh-branch" />
                </Label>
                <Input
                  id="gh-branch"
                  data-testid="gh-branch"
                  value={form.branch}
                  onChange={(e) => setForm({ ...form, branch: e.target.value })}
                  className="mt-1 rounded-sm"
                />
              </div>

              <div className="flex items-center gap-2 pt-2">
                <Button
                  data-testid="gh-save-btn"
                  onClick={handleSave}
                  disabled={saving}
                  className="bg-[#0A2540] text-white hover:bg-[#021122] rounded-sm"
                >
                  {saving ? "Saving…" : "Save GitHub Config"}
                </Button>
                <Button
                  data-testid="gh-test-btn"
                  onClick={handleTest}
                  disabled={testing}
                  variant="outline"
                  className="bg-white border-slate-300 hover:bg-slate-50 text-slate-700 rounded-sm"
                >
                  <Cloud className="w-4 h-4 mr-1" />
                  {testing ? "Testing…" : "Test Connection"}
                </Button>
                {testResult && (
                  <div className={`flex items-center gap-1 text-xs ${testResult.ok ? "text-emerald-700" : "text-red-700"}`} data-testid="gh-test-result">
                    {testResult.ok ? <CheckCircle2 className="w-4 h-4" /> : <XCircle className="w-4 h-4" />}
                    {testResult.ok ? `${testResult.repo_name} (${testResult.default_branch})` : testResult.error}
                  </div>
                )}
              </div>
            </div>
          </section>

          {/* Section B — Folder Tree Preview */}
          {saved && (
            <section className="mos-panel p-6" data-testid="section-folder-tree">
              <div className="flex items-start justify-between mb-3">
                <div>
                  <h2 className="font-display text-sm font-bold tracking-tight text-[#0A2540] flex items-center">
                    <Folder className="w-4 h-4 mr-1.5" />
                    Target Folder Structure
                    <HelpIcon text="LAMA will push this structure to GitHub in Stage 4 (Code Generation). Schema files are pushed after Stage 2 (Data Model)." testId="help-folder-tree" />
                  </h2>
                  <p className="text-xs text-slate-500 mt-1">Read-only preview of what will be committed at each stage.</p>
                </div>
                <Button
                  data-testid="push-srs-btn"
                  onClick={handlePushSRS}
                  disabled={pushing}
                  className="bg-[#0A2540] text-white hover:bg-[#021122] rounded-sm text-xs h-8"
                >
                  {pushing ? "Pushing…" : "Push SRS to GitHub"}
                </Button>
              </div>
              <pre
                data-testid="folder-tree"
                className="bg-slate-50 border border-slate-200 rounded-sm p-4 text-[12px] font-mono text-slate-800 overflow-x-auto leading-relaxed"
              >
{FOLDER_TREE}
              </pre>
              <div className="mt-3 text-[11px] text-slate-500 space-y-1">
                <div>· <b>Stage 1 (SRS freeze):</b> pushes <code>docs/SRS.md</code></div>
                <div>· <b>Stage 2 (DataModel freeze):</b> pushes <code>schema/*.sql</code></div>
                <div>· <b>Stage 4 (CodeGen):</b> pushes full <code>backend/</code> + <code>frontend/</code> + Dockerfile</div>
              </div>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
