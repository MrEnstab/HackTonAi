"use client";
import { useEffect, useState } from "react";
import { type Project, readJson } from "./lib";

export function useProjects() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [projectError, setProjectError] = useState("");
  useEffect(() => {
    let active = true;
    fetch("/api/projects")
      .then((r) => readJson<{ projects: Project[] }>(r))
      .then((data) => {
        if (!active) return;
        setProjects(data.projects);
        const wanted = new URLSearchParams(window.location.search).get(
          "project",
        );
        if (wanted && !data.projects.some((p) => String(p.id) === wanted)) {
          setProjectError("Проект из ссылки не найден. Выберите другой.");
          return;
        }
        setProjectId(wanted || String(data.projects[0]?.id || ""));
      })
      .catch((e) => active && setProjectError(e.message));
    return () => {
      active = false;
    };
  }, []);
  function choose(id: string) {
    setProjectId(id);
    setProjectError("");
    const url = new URL(window.location.href);
    url.searchParams.set("project", id);
    url.searchParams.delete("observation");
    window.history.replaceState(null, "", url);
  }
  return {
    projects,
    setProjects,
    projectId,
    choose,
    projectError,
    setProjectError,
  };
}

export default function ProjectPicker({
  state,
  disabled = false,
}: {
  state: ReturnType<typeof useProjects>;
  disabled?: boolean;
}) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  async function create() {
    if (!name.trim()) {
      state.setProjectError("Введите название проекта.");
      return;
    }
    setBusy(true);
    state.setProjectError("");
    try {
      const { project } = await readJson<{ project: Project }>(
        await fetch("/api/projects", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name }),
        }),
      );
      state.setProjects((p) => [...p, project]);
      state.choose(String(project.id));
      setName("");
    } catch (e) {
      state.setProjectError(
        e instanceof Error ? e.message : "Не удалось создать проект.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="my-6 rounded-2xl border border-border bg-surface p-5">
      <label htmlFor="project" className="mb-2 block font-semibold text-main">
        Проект
      </label>
      <select
        id="project"
        value={state.projectId}
        onChange={(e) => state.choose(e.target.value)}
        disabled={busy || disabled}
        className="w-full rounded-xl border border-border bg-white p-3 text-main"
      >
        <option value="">Выберите проект</option>
        {state.projects.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
      </select>
      <div className="mt-3 flex flex-wrap gap-2">
        <input
          aria-label="Название нового проекта"
          placeholder="Название нового проекта"
          maxLength={120}
          value={name}
          onChange={(e) => setName(e.target.value)}
          disabled={busy || disabled}
          className="min-w-0 flex-1 rounded-xl border border-border bg-white p-3 text-main"
        />
        <button
          type="button"
          onClick={create}
          disabled={busy || disabled}
          className="rounded-xl bg-button px-4 py-3 text-button-text disabled:opacity-50"
        >
          {busy ? "Создаём…" : "+ Создать проект"}
        </button>
      </div>
      {state.projectError && (
        <p role="alert" className="mt-3 text-danger">
          {state.projectError}
        </p>
      )}
    </section>
  );
}
