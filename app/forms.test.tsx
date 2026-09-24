import { expect, mock, test } from "bun:test";
import { renderToStaticMarkup } from "react-dom/server";

mock.module("next/navigation", () => ({ useRouter: () => ({ push() {} }) }));
const { default: CreateTask } = await import("./create-task/page");
const { default: Home } = await import("./page");
const { default: Results } = await import("./results/page");
test("results show saved date-project analyses rather than a stock video", () => {
  const html = renderToStaticMarkup(<Results />);
  expect(html).toContain("Дата и проект");
  expect(html).toContain("Выберите созданную дату");
  expect(html).not.toContain("video-preview");
});

test("planning asks for project name with date and equipment quantities", () => {
  const html = renderToStaticMarkup(<CreateTask />);
  expect((html.match(/type="number"/g) || []).length).toBe(6);
  expect(html).toContain("Название проекта");
  expect(html).toContain("Дата плана");
  expect(html).not.toContain("+ Создать проект");
});

test("upload chooses one date-project schedule and photo time", () => {
  const html = renderToStaticMarkup(<Home />);
  expect(html).toContain("Дата и проект");
  expect(html).toContain("Время снимка");
  expect(html).not.toContain("+ Создать проект");
});

test("results reopen a saved date-project analysis", () => {
  const html = renderToStaticMarkup(<Results />);
  expect(html).toContain("Дата и проект");
  expect(html).toContain("Техника на графике");
  expect(html).not.toContain("+ Создать проект");
});
