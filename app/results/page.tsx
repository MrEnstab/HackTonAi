"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import {
  EQUIPMENT,
  type EquipmentType,
  formatTimestamp,
  type Report,
  readJson,
} from "../lib";
import HistoryChart from "../result/chart-placeholder";
import { scheduleLabel, useSchedules } from "../schedules";

export default function ResultsPage() {
  const { schedules, loading, error: scheduleError } = useSchedules();
  const [scheduleKey, setScheduleKey] = useState("");
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [equipment, setEquipment] = useState<EquipmentType>("excavator");

  useEffect(() => {
    if (!schedules.length || scheduleKey) return;
    const query = new URLSearchParams(window.location.search);
    const wanted = `${query.get("project")}:${query.get("date")}`;
    setSelectedId(Number(query.get("observation")) || null);
    setScheduleKey(
      schedules.some((item) => item.key === wanted) ? wanted : schedules[0].key,
    );
  }, [schedules, scheduleKey]);

  const schedule = schedules.find((item) => item.key === scheduleKey);
  const date = schedule?.plan.date || "";

  useEffect(() => {
    let active = true;
    setReport(null);
    setError("");
    if (!schedule) return;
    fetch(`/api/projects/${schedule.project.id}/report`)
      .then((response) => readJson<Report>(response))
      .then((data) => active && setReport(data))
      .catch((reason: Error) => active && setError(reason.message));
    return () => {
      active = false;
    };
  }, [schedule]);

  const observations =
    report?.observations.filter(
      (observation) => observation.observedAt.slice(0, 10) === date,
    ) || [];
  const latest = observations.at(-1);
  const selected =
    observations.find((observation) => observation.id === selectedId) || latest;
  const max = Math.max(
    1,
    ...(selected?.comparison.flatMap((item) => [item.planned, item.actual]) ||
      []),
  );

  function chooseSchedule(value: string) {
    setScheduleKey(value);
    setSelectedId(null);
    const next = schedules.find((item) => item.key === value);
    const url = new URL(window.location.href);
    if (next) {
      url.searchParams.set("project", String(next.project.id));
      url.searchParams.set("date", next.plan.date);
    }
    url.searchParams.delete("observation");
    window.history.replaceState(null, "", url);
  }
  return (
    <div className="min-h-screen bg-page px-4 py-10">
      <div className="mx-auto max-w-5xl">
        <nav className="flex flex-wrap gap-4 text-muted">
          <Link
            href={
              schedule ? `/?project=${schedule.project.id}&date=${date}` : "/"
            }
            className="hover:underline"
          >
            ← Загрузить ещё фото
          </Link>
          <Link
            href={
              schedule
                ? `/create-task?project=${schedule.project.id}&date=${date}`
                : "/create-task"
            }
            className="hover:underline"
          >
            Создать или изменить дату
          </Link>
        </nav>
        <h1 className="mt-5 text-3xl font-bold text-main">
          Статистика и графики проекта
        </h1>
        <p className="mt-2 text-muted">
          Реальные сохранённые проверки. Повторные снимки не суммируются в
          количество техники.
        </p>
        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          <label className="font-semibold text-main">
            Дата и проект
            <select
              aria-label="Дата и проект"
              value={scheduleKey}
              onChange={(event) => chooseSchedule(event.target.value)}
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
          <label className="font-semibold text-main">
            Техника на графике
            <select
              aria-label="Техника на графике"
              value={equipment}
              onChange={(e) => setEquipment(e.target.value as EquipmentType)}
              className="mt-2 block w-full rounded-xl border border-border bg-white p-3 font-normal"
            >
              {EQUIPMENT.map((e) => (
                <option key={e.type} value={e.type}>
                  {e.label}
                </option>
              ))}
            </select>
          </label>
        </div>
        {(error || scheduleError) && (
          <p role="alert" className="mt-4 text-danger">
            {error || scheduleError}
          </p>
        )}
        {(loading || (!report && schedule)) && !error && !scheduleError && (
          <p className="mt-4 text-muted">Загружаем сохранённый анализ…</p>
        )}
        {!loading && !schedules.length && (
          <p className="mt-5 rounded-2xl bg-surface p-5 text-muted">
            Созданных дат пока нет.{" "}
            <Link href="/create-task" className="underline">
              Создать дату
            </Link>
          </p>
        )}
        {report && (
          <>
            <div className="mt-6 grid gap-3 sm:grid-cols-3">
              <div className="rounded-2xl bg-surface p-5">
                <p className="text-muted">Проверок за период</p>
                <strong className="text-2xl text-main">
                  {observations.length}
                </strong>
              </div>
              <div className="rounded-2xl bg-surface p-5">
                <p className="text-muted">На последнем снимке</p>
                <strong className="text-2xl text-main">
                  {latest ? `${latest.total} ед.` : "Нет данных"}
                </strong>
              </div>
              <div className="rounded-2xl bg-surface p-5">
                <p className="text-muted">Последний снимок · МСК</p>
                <strong className="text-main">
                  {latest ? formatTimestamp(latest.observedAt) : "Нет данных"}
                </strong>
              </div>
            </div>
            <HistoryChart observations={observations} equipment={equipment} />
            <p className="mt-4 text-sm text-muted">
              «Не обнаружено» не доказывает физическое отсутствие: техника может
              быть вне кадра или не распознана. График соединяет только
              имеющиеся проверки, а не непрерывные наблюдения.
            </p>
            {!observations.length && date && (
              <div className="mt-5 rounded-2xl border border-border p-5 text-main">
                {report.plans.find((p) => p.date === date)
                  ? "План на дату есть, но фото ещё не проверялись."
                  : "На эту дату нет плана и проверок."}{" "}
                <Link
                  href={
                    schedule
                      ? `/?project=${schedule.project.id}&date=${date}`
                      : "/"
                  }
                  className="underline"
                >
                  Добавить снимок
                </Link>
              </div>
            )}
            {!!observations.length && (
              <>
                <h2 className="mt-8 text-xl font-bold text-main">
                  История проверок · МСК (UTC+03:00)
                </h2>
                <div className="mt-3 overflow-x-auto rounded-2xl border border-border">
                  <table className="w-full text-left text-sm">
                    <thead className="bg-surface text-muted">
                      <tr>
                        <th className="p-3">Дата и время</th>
                        <th className="p-3">Снимок / зона</th>
                        <th className="p-3">Распознано</th>
                        <th className="p-3">Проверка этапа</th>
                      </tr>
                    </thead>
                    <tbody>
                      {observations.map((o) => (
                        <tr
                          key={o.id}
                          className={`border-t border-border ${selected?.id === o.id ? "bg-success-bg" : "bg-white"}`}
                        >
                          <td className="p-3">
                            <button
                              type="button"
                              onClick={() => setSelectedId(o.id)}
                              className="whitespace-nowrap font-semibold text-main underline"
                            >
                              {formatTimestamp(o.observedAt)}
                            </button>
                          </td>
                          <td className="max-w-60 break-words p-3 text-main">
                            {o.sourceFilename}
                            <br />
                            <span className="text-muted">
                              {o.planSnapshot.zone || "Зона не указана"}
                            </span>
                          </td>
                          <td className="p-3 text-main">{o.total}</td>
                          <td
                            className={`p-3 ${o.warnings.length ? "text-danger" : "text-success"}`}
                          >
                            {o.warnings.length
                              ? `Предупреждений: ${o.warnings.length}`
                              : "Соответствует"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
            {selected && (
              <section className="mt-8 rounded-2xl border border-border bg-white p-5">
                <h2 className="text-xl font-bold text-main">
                  Проверка от {formatTimestamp(selected.observedAt)} · МСК
                </h2>
                <p className="mt-2 text-muted">
                  Этап: {selected.planSnapshot.stage} · Зона:{" "}
                  {selected.planSnapshot.zone || "не указана"}
                </p>
                <p className="text-sm text-muted">
                  {selected.planSnapshot.taskName} · План сохранён вместе с
                  проверкой, поздние правки его не меняют.
                </p>
                {selected.snapshotProvenance === "legacy_plan_at_migration" && (
                  <p className="mt-3 text-sm text-danger">
                    Старая проверка: исходное фото не сохранялось; план
                    восстановлен на момент миграции, прежние изменения
                    неизвестны.
                  </p>
                )}
                <div className="mt-5 grid gap-6 md:grid-cols-2">
                  <div>
                    <h3 className="mb-3 font-semibold text-main">
                      План / распознано на выбранном фото
                    </h3>
                    <table className="w-full text-left text-sm">
                      <thead>
                        <tr className="text-muted">
                          <th className="py-2">Техника</th>
                          <th>План</th>
                          <th>Фото</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selected.comparison.map((c) => (
                          <tr key={c.type} className="border-t border-border">
                            <td className="py-3 pr-3 text-main">
                              {c.label}
                              <div className="mt-2 h-1.5 rounded bg-surface">
                                <div
                                  className="h-full rounded bg-button"
                                  style={{
                                    width: `${(c.planned / max) * 100}%`,
                                  }}
                                />
                              </div>
                              <div className="mt-1 h-1.5 rounded bg-surface">
                                <div
                                  className="h-full rounded bg-accent"
                                  style={{
                                    width: `${(c.actual / max) * 100}%`,
                                  }}
                                />
                              </div>
                            </td>
                            <td>{c.planned}</td>
                            <td
                              className={
                                c.missing || c.unexpected
                                  ? "text-danger"
                                  : "text-success"
                              }
                            >
                              {c.actual}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    <div
                      className={`mt-4 rounded-xl p-4 ${selected.warnings.length ? "bg-danger-bg" : "bg-success-bg"}`}
                    >
                      {selected.warnings.length ? (
                        <ul className="space-y-2 text-sm text-main">
                          {selected.warnings.map((w) => (
                            <li key={`${w.kind}-${w.type}`}>
                              {w.kind === "unexpected"
                                ? "⚠ Непредусмотренный тип. "
                                : "⚠ Требуемая техника. "}
                              {w.message}
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="text-success">
                          Техника на снимке соответствует плану этапа.
                        </p>
                      )}
                    </div>
                  </div>
                  <div>
                    {selected.evidenceUrl ? (
                      <a
                        href={`/api${selected.evidenceUrl}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        <img
                          src={`/api${selected.evidenceUrl}`}
                          alt={`Фото-доказательство: ${selected.sourceFilename}`}
                          className="max-h-96 w-full rounded-xl object-contain"
                        />
                        <p className="mt-2 text-sm text-muted">
                          Открыть сохранённое фото
                        </p>
                      </a>
                    ) : (
                      <p className="rounded-xl bg-surface p-8 text-muted">
                        Фото-доказательство для старой проверки отсутствует.
                      </p>
                    )}
                  </div>
                </div>
              </section>
            )}
          </>
        )}
      </div>
    </div>
  );
}
