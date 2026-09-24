import { expect, test } from "bun:test";
import { renderToStaticMarkup } from "react-dom/server";
import Chart from "./result/chart-placeholder";

const observations = [
  {
    id: 1,
    observedAt: "2026-09-18T09:00:00+03:00",
    counts: { excavator: 1 },
    planned: { excavator: 2 },
  },
  {
    id: 2,
    observedAt: "2026-09-18T10:00:00+03:00",
    counts: { excavator: 0 },
    planned: { excavator: 2 },
  },
  {
    id: 3,
    observedAt: "2026-09-19T09:00:00+03:00",
    counts: { excavator: 3 },
    planned: { excavator: 4 },
  },
];

test("chart plots individual checks against elapsed time, with real planned snapshots", () => {
  const html = renderToStaticMarkup(
    <Chart observations={observations as never} equipment="excavator" />,
  );
  expect(html).toContain("<svg");
  expect(html).toContain('data-time="2026-09-19T09:00:00+03:00"');
  expect(html).toContain('data-actual="0"');
  expect(html).toContain('data-planned="4"');
  const xs = [...html.matchAll(/data-x="([\d.]+)"/g)].map((m) => Number(m[1]));
  expect(xs.length).toBe(3);
  expect((xs[1] - xs[0]) / (xs[2] - xs[0])).toBeCloseTo(1 / 24, 4);
});

test("empty history is no data, not proof of zero equipment", () => {
  const html = renderToStaticMarkup(
    <Chart observations={[]} equipment="excavator" />,
  );
  expect(html).toContain("Проверок пока нет");
  expect(html).not.toContain("<svg");
});
