import {
  EQUIPMENT,
  type EquipmentType,
  formatTimestamp,
  type Observation,
} from "../lib";

export default function HistoryChart({
  observations,
  equipment,
}: {
  observations: Observation[];
  equipment: EquipmentType;
}) {
  if (!observations.length)
    return (
      <div className="mt-6 rounded-2xl bg-surface p-8 text-muted">
        Проверок пока нет. Наличие техники ещё не оценивалось.
      </div>
    );
  const points = [...observations].sort(
    (a, b) =>
      Date.parse(a.observedAt) - Date.parse(b.observedAt) || a.id - b.id,
  );
  const start = Date.parse(points[0].observedAt),
    end = Date.parse(points[points.length - 1].observedAt);
  const max = Math.max(
    1,
    ...points.flatMap((p) => [
      p.counts[equipment] || 0,
      p.planned[equipment] || 0,
    ]),
  );
  const x = (p: Observation) =>
    end === start
      ? 400
      : 60 + ((Date.parse(p.observedAt) - start) / (end - start)) * 680;
  const y = (n: number) => 220 - (n / max) * 170;
  const actual = points
    .map((p) => `${x(p)},${y(p.counts[equipment] || 0)}`)
    .join(" ");
  const planned = points
    .map((p) => `${x(p)},${y(p.planned[equipment] || 0)}`)
    .join(" ");
  const label = EQUIPMENT.find((e) => e.type === equipment)?.label;
  return (
    <div className="mt-6 rounded-2xl bg-surface p-4">
      <p className="text-sm text-muted">
        {label} · единиц на отдельном снимке · время МСК (UTC+03:00)
      </p>
      <svg
        viewBox="0 0 800 285"
        role="img"
        aria-label={`История проверок: ${label}`}
        className="w-full min-w-0"
      >
        <title>Распознано и требовалось в момент каждой проверки</title>
        {[0, max].map((n) => (
          <g key={n}>
            <line x1="60" x2="740" y1={y(n)} y2={y(n)} stroke="#d4d4d4" />
            <text x="45" y={y(n) + 5} textAnchor="end" fontSize="14">
              {n}
            </text>
          </g>
        ))}
        <polyline
          points={planned}
          fill="none"
          stroke="#6b7280"
          strokeWidth="2"
          strokeDasharray="7 5"
        />
        <polyline
          points={actual}
          fill="none"
          stroke="#258365"
          strokeWidth="3"
        />
        {points.map((p) => (
          <g
            key={p.id}
            data-time={p.observedAt}
            data-actual={p.counts[equipment] || 0}
            data-planned={p.planned[equipment] || 0}
            data-x={x(p)}
          >
            <circle
              cx={x(p)}
              cy={y(p.planned[equipment] || 0)}
              r="4"
              fill="#6b7280"
            />
            <circle
              cx={x(p)}
              cy={y(p.counts[equipment] || 0)}
              r="5"
              fill="#258365"
            >
              <title>{`${formatTimestamp(p.observedAt)} · распознано ${p.counts[equipment] || 0}, план ${p.planned[equipment] || 0}`}</title>
            </circle>
          </g>
        ))}
        <text x="60" y="250" fontSize="13">
          {formatTimestamp(points[0].observedAt)}
        </text>
        {points.length > 1 && (
          <text x="740" y="250" textAnchor="end" fontSize="13">
            {formatTimestamp(points[points.length - 1].observedAt)}
          </text>
        )}
      </svg>
      <p className="text-sm text-muted">
        <span className="text-success">● Распознано</span> ·{" "}
        <span>┄ План на момент проверки</span>. Точки — отдельные фото, не сумма
        техники и не учёт заездов.
      </p>
    </div>
  );
}
