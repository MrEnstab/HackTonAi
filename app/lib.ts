export const EQUIPMENT = [
  { type: "excavator", label: "Экскаватор" },
  { type: "dump_truck", label: "Самосвал" },
  { type: "wheel_loader", label: "Фронтальный погрузчик" },
  { type: "motor_grader", label: "Автогрейдер" },
  { type: "concrete_mixer", label: "Автобетоносмеситель" },
  { type: "mobile_crane", label: "Автомобильный кран" },
] as const;

export type EquipmentType = (typeof EQUIPMENT)[number]["type"];
export type PlanItem = { type: EquipmentType; label: string; quantity: number };
export type Project = { id: number; name: string };
export type Plan = {
  id: number;
  projectId: number;
  date: string;
  taskName: string;
  stage: string;
  zone: string;
  startTime: string;
  items: PlanItem[];
};
export type PlanSummary = Plan;
export type Comparison = {
  type: EquipmentType;
  label: string;
  planned: number;
  actual: number;
  missing: number;
  unexpected: number;
  complete: boolean;
};
export type Observation = {
  id: number;
  projectId: number;
  observedAt: string;
  sourceFilename: string;
  counts: Record<EquipmentType, number>;
  planned: Partial<Record<EquipmentType, number>>;
  total: number;
  evidenceUrl: string | null;
  planSnapshot: Plan;
  comparison: Comparison[];
  warnings: {
    kind: "missing" | "unexpected";
    type: EquipmentType;
    quantity: number;
    message: string;
  }[];
  isComplete: boolean;
  snapshotProvenance: string;
};
export type Report = {
  project: Project;
  plans: Plan[];
  observations: Observation[];
  latestObservation: Observation | null;
  savedObservationId?: number;
  timezoneLabel: string;
};

export function formatTimestamp(value: string) {
  return new Date(value).toLocaleString("ru-RU", {
    timeZone: "Europe/Moscow",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export async function readJson<T>(response: Response): Promise<T> {
  const text = await response.text();
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch {
    throw new Error(`Некорректный ответ сервера (HTTP ${response.status})`);
  }
  if (!response.ok)
    throw new Error(
      (data as { error?: string }).error || `HTTP ${response.status}`,
    );
  return data as T;
}

export function isoDate(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}
