"use client";

import { useEffect, useState } from "react";
import { type Plan, type Project, readJson } from "./lib";

export type Schedule = { key: string; project: Project; plan: Plan };

export function scheduleLabel(schedule: Schedule) {
  return `${schedule.plan.date.split("-").reverse().join(".")} — ${schedule.project.name}`;
}

export function useSchedules() {
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    async function load() {
      setLoading(true);
      setError("");
      try {
        const { projects } = await readJson<{ projects: Project[] }>(
          await fetch("/api/projects"),
        );
        const groups = await Promise.all(
          projects.map(async (project) => {
            const { plans } = await readJson<{ plans: Plan[] }>(
              await fetch(`/api/projects/${project.id}/plans`),
            );
            return plans.map((plan) => ({
              key: `${project.id}:${plan.date}`,
              project,
              plan,
            }));
          }),
        );
        if (active) {
          setSchedules(
            groups
              .flat()
              .sort(
                (a, b) =>
                  b.plan.date.localeCompare(a.plan.date) ||
                  a.project.name.localeCompare(b.project.name, "ru"),
              ),
          );
        }
      } catch (reason) {
        if (active) {
          setError(
            reason instanceof Error
              ? reason.message
              : "Не удалось загрузить даты.",
          );
        }
      } finally {
        if (active) setLoading(false);
      }
    }
    load();
    return () => {
      active = false;
    };
  }, []);

  return { schedules, loading, error };
}
