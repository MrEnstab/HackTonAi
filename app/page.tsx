"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { type Report, readJson } from "./lib";
import { scheduleLabel, useSchedules } from "./schedules";

function currentTime() {
  const now = new Date();
  return `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
}

export default function Home() {
  const router = useRouter();
  const { schedules, loading, error: scheduleError } = useSchedules();
  const [scheduleKey, setScheduleKey] = useState("");
  const [time, setTime] = useState(currentTime);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!schedules.length || scheduleKey) return;
    const query = new URLSearchParams(window.location.search);
    const wanted = `${query.get("project")}:${query.get("date")}`;
    setScheduleKey(
      schedules.some((item) => item.key === wanted) ? wanted : schedules[0].key,
    );
  }, [schedules, scheduleKey]);

  const schedule = schedules.find((item) => item.key === scheduleKey);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!file || !schedule) {
      setError("Выберите созданную дату и фотографию.");
      return;
    }
    setBusy(true);
    setError("");
    const body = new FormData();
    body.append("file", file);
    body.append("observedAt", `${schedule.plan.date}T${time}`);
    try {
      const report = await readJson<Report>(
        await fetch(`/api/projects/${schedule.project.id}/observations`, {
          method: "POST",
          body,
        }),
      );
      router.push(
        `/results?project=${schedule.project.id}&date=${schedule.plan.date}&observation=${report.savedObservationId}`,
      );
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Не удалось обработать снимок.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-page px-4 py-10">
      <div className="w-full max-w-4xl rounded-sm bg-white px-6 py-10 sm:px-14">
        <nav className="flex flex-wrap justify-center gap-3">
          <Link
            href={
              schedule
                ? `/results?project=${schedule.project.id}&date=${schedule.plan.date}`
                : "/results"
            }
            className="rounded-full border border-border px-4 py-2 text-main"
          >
            Результаты и графики
          </Link>
          <Link
            href="/create-task"
            className="rounded-full border border-border px-4 py-2 text-main"
          >
            Создать дату
          </Link>
        </nav>
        <h1 className="mt-8 text-3xl font-bold text-main">Загрузить фото</h1>
        <p className="mt-2 text-muted">
          Выберите созданную дату проекта, загрузите фото и укажите время
          снимка.
        </p>

        <form onSubmit={submit} className="mt-7 space-y-5">
          <fieldset disabled={busy} className="space-y-5">
            <label className="block font-semibold text-main">
              Дата и проект
              <select
                aria-label="Дата и проект"
                required
                value={scheduleKey}
                onChange={(event) => setScheduleKey(event.target.value)}
                className="mt-2 block w-full rounded-xl border border-border bg-white p-3 font-normal"
              >
                <option value="">Выберите созданную дату</option>
                {schedules.map((item) => (
                  <option key={item.key} value={item.key}>
                    {scheduleLabel(item)}
                  </option>
                ))}
              </select>
            </label>
            {loading && <p className="text-muted">Загружаем даты…</p>}
            {!loading && !schedules.length && (
              <p className="rounded-xl bg-surface p-4 text-muted">
                Созданных дат пока нет.{" "}
                <Link href="/create-task" className="underline">
                  Создать первую дату
                </Link>
              </p>
            )}
            <label className="flex cursor-pointer flex-col items-center rounded-2xl border border-dashed border-border bg-surface p-8 text-center">
              <Image src="/main/image.svg" alt="" width={32} height={32} />
              <span className="my-3 text-main">
                {file?.name || "Выберите фото JPG или PNG"}
              </span>
              <input
                aria-label="Фото для проверки"
                type="file"
                accept="image/jpeg,image/png"
                required
                onChange={(event) => setFile(event.target.files?.[0] || null)}
                className="max-w-full text-sm text-muted"
              />
            </label>
            <label className="block font-semibold text-main">
              Время снимка · МСК
              <input
                aria-label="Время снимка"
                type="time"
                required
                value={time}
                onChange={(event) => setTime(event.target.value)}
                className="mt-2 block w-full rounded-xl border border-border bg-white p-3 font-normal"
              />
            </label>
            {schedule && (
              <p className="rounded-xl bg-surface p-4 text-main">
                План:{" "}
                {schedule.plan.items
                  .map((item) => `${item.label}: ${item.quantity}`)
                  .join(" · ")}
              </p>
            )}
          </fieldset>
          {(error || scheduleError) && (
            <p role="alert" className="text-danger">
              {error || scheduleError}
            </p>
          )}
          <button
            type="submit"
            disabled={busy || !schedule || !file}
            className="w-full rounded-xl bg-button py-3.5 font-medium text-button-text disabled:opacity-40"
          >
            {busy ? "Распознаём и сохраняем…" : "Проверить и сохранить →"}
          </button>
        </form>
      </div>
    </div>
  );
}
