import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { listProjects, createProject as apiCreateProject } from "@/lib/api";

const ProjectContext = createContext(null);

export function ProjectProvider({ children }) {
  const [projects, setProjects] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listProjects();
      setProjects(data);
      if (!activeId && data.length > 0) {
        setActiveId(data[0].id);
      }
    } finally {
      setLoading(false);
    }
  }, [activeId]);

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const create = async (payload) => {
    const p = await apiCreateProject(payload);
    await refresh();
    setActiveId(p.id);
    return p;
  };

  const active = projects.find((p) => p.id === activeId) || null;

  return (
    <ProjectContext.Provider value={{ projects, active, activeId, setActiveId, refresh, create, loading }}>
      {children}
    </ProjectContext.Provider>
  );
}

export const useProjects = () => {
  const ctx = useContext(ProjectContext);
  if (!ctx) throw new Error("useProjects must be inside ProjectProvider");
  return ctx;
};
