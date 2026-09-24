"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  EQUIPMENT,
  type EquipmentType,
  isoDate,
  type Plan,
  type Project,
  readJson,
} from "../lib";

export default function CreateTaskPage() {
  const router = useRouter();
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectName, setProjectName] = useState("");
  const [date, setDate] = useState("");
  const [quantities, setQuantities] = useState<
    Partial<Record<EquipmentType, number>>
  >({});
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [exists, setExists] = useState(false);

  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    const requestedProject = Number(query.get("project"));
    setDate(query.get("date") || isoDate(new Date()));
    fetch("/api/projects")
      .then((response) => readJson<{ projects: Project[] }>(response))
      .then(({ projects: items }) => {
        setProjects(items);
        const selected = items.find((item) => item.id === requestedProject);
        if (selected) setProjectName(selected.name);
      })
      .catch((reason: Error) => setError(reason.message));
  }, []);

  useEffect(() => {
    const project = projects.find(
      (item) =>
        item.name.toLocaleLowerCase("ru") ===
        projectName.trim().toLocaleLowerCase("ru"),
    );
    setExists(false);
    if (!project || !date) return;
    let active = true;
    setLoading(true);
    fetch(`/api/projects/${project.id}/plans/${date}`)
      .then(async (response) =>
        response.status === 404 ? null : readJson<{ plan: Plan }>(response),
      )
      .then((data) => {
        if (!active || !data) return;
        setQuantities(
          Object.fromEntries(
            data.plan.items.map((item) => [item.type, item.quantity]),
          ),
        );
        setExists(true);
      })
      .catch((reason: Error) => active && setError(reason.message))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [date, projectName, projects]);

  function setQuantity(type: EquipmentType, value: number) {
    setQuantities((current) => ({
      ...current,
      [type]: Math.max(0, Math.min(999, Math.floor(value || 0))),
    }));
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    const name = projectName.trim();
    const items = EQUIPMENT.filter(
      (item) => (quantities[item.type] || 0) > 0,
    ).map((item) => ({ type: item.type, quantity: quantities[item.type] }));
    if (!name) {
      setError("Введите название проекта.");
      return;
    }
    if (!items.length) {
      setError("Укажите хотя бы одну единицу техники.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      let project = projects.find(
        (item) =>
          item.name.toLocaleLowerCase("ru") === name.toLocaleLowerCase("ru"),
      );
      if (!project) {
        const created = await readJson<{ project: Project }>(
          await fetch("/api/projects", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name }),
          }),
        );
        project = created.project;
      }
      await readJson(
        await fetch(`/api/projects/${project.id}/plans/${date}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            taskName: `План техники: ${name}`,
            stage: "Плановая проверка",
            zone: "",
            startTime: "00:00",
            items,
          }),
        }),
      );
      router.push(`/?project=${project.id}&date=${date}`);
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Не удалось сохранить дату.",
      );
    } finally {
      setBusy(false);
    }
  }

  const total = Object.values(quantities).reduce(
    (sum, value) => sum + (value || 0),
    0,
  );

  return (
    <div className="min-h-screen bg-page px-4 py-10">
      <div className="mx-auto w-full max-w-4xl">
        <Link href="/" className="text-muted hover:underline">
          ← К загрузке фото
        </Link>
        <h1 className="mt-4 text-3xl font-bold text-main">
          Запланировать технику
        </h1>
        <p className="mt-2 text-muted">
          Введите название проекта, дату и требуемое количество техники.
        </p>
        <form onSubmit={save} className="mt-7 space-y-6">
          <fieldset disabled={busy} className="grid gap-4 sm:grid-cols-2">
            <label className="font-semibold text-main">
              Название проекта
              <input
                aria-label="Название проекта"
                list="project-names"
                required
                maxLength={120}
                value={projectName}
                onChange={(event) => {
                  setProjectName(event.target.value);
                  setQuantities({});
                }}
                placeholder="Например: ЖК Северный"
                className="mt-2 block w-full rounded-xl border border-border bg-white p-3 font-normal"
              />
              <datalist id="project-names">
                {projects.map((project) => (
                  <option key={project.id} value={project.name} />
                ))}
              </datalist>
            </label>
            <label className="font-semibold text-main">
              Дата плана
              <input
                aria-label="Дата плана"
                type="date"
                required
                value={date}
                onChange={(event) => {
                  setDate(event.target.value);
                  setQuantities({});
                }}
                className="mt-2 block w-full rounded-xl border border-border bg-white p-3 font-normal"
              />
            </label>
          </fieldset>

          {loading && <p className="text-muted">Загружаем сохранённый план…</p>}
          <fieldset disabled={busy || loading}>
            <h2 className="text-xl font-bold text-main">
              Техника{" "}
              <span className="text-base font-normal text-muted">
                · {total} ед.
              </span>
            </h2>
            <p className="mt-1 text-sm text-muted">
              Укажите количество кнопками или введите число.
            </p>
            <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {EQUIPMENT.map((item) => {
                const value = quantities[item.type] || 0;
                return (
                  <div
                    key={item.type}
                    className={`rounded-2xl border p-4 ${value ? "border-success bg-success-bg" : "border-border bg-white"}`}
                  >
                    <label
                      htmlFor={`qty-${item.type}`}
                      className="block min-h-12 font-semibold text-main"
                    >
                      {item.label}
                    </label>
                    <div className="mt-3 flex items-center gap-2">
                      <button
                        type="button"
                        aria-label={`Уменьшить: ${item.label}`}
                        disabled={!value}
                        onClick={() => setQuantity(item.type, value - 1)}
                        className="h-10 w-10 rounded-xl border border-border bg-white text-xl disabled:opacity-30"
                      >
                        −
                      </button>
                      <input
                        id={`qty-${item.type}`}
                        aria-label={`Количество: ${item.label}`}
                        type="number"
                        min={0}
                        max={999}
                        value={value}
                        onChange={(event) =>
                          setQuantity(item.type, Number(event.target.value))
                        }
                        className="h-10 min-w-0 flex-1 rounded-xl border border-border bg-white text-center text-main"
                      />
                      <button
                        type="button"
                        aria-label={`Увеличить: ${item.label}`}
                        onClick={() => setQuantity(item.type, value + 1)}
                        className="h-10 w-10 rounded-xl bg-button text-xl text-button-text"
                      >
                        +
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </fieldset>
          {exists && (
            <p className="text-sm text-muted">
              Эта дата уже создана. Сохранение обновит план, а старые анализы
              останутся без изменений.
            </p>
          )}
          {error && (
            <p role="alert" className="text-danger">
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={busy || loading}
            className="w-full rounded-xl bg-accent py-3.5 font-medium text-accent-text disabled:opacity-40"
          >
            {busy ? "Сохраняем…" : "Сохранить дату и перейти к фото"}
          </button>
        </form>
      </div>
    </div>
  );
}
