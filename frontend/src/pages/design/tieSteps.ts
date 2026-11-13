// Палитра ступеней правки коммутации на плане (TASK-017, PR 4).
//
// Номиналы — из каталога сервера (`GET /design/tie/catalog`, константы
// `design/timing.py`), у каждого номинала — свой цвет по порядку. Цвет одной
// ступени на плане, в палитре над планом и в легенде панели — один.
import type { InitiationNetwork, SystemType, TieCatalog, TieSystemCatalog } from "../../types/design";

/** Цвета номиналов по порядку (1–5); номиналов больше — по кругу. */
export const STEP_COLORS = ["#2f8f5b", "#2f6fd0", "#c0392b", "#8e44ad", "#d68910"] as const;
/** Ступень вне номиналов системы (своё значение у электронной, старые сети). */
export const OFF_NOMINAL_COLOR = "#7d8a84";

/** Ступень по умолчанию, если в сети нет `trunk_ms`. */
export const DEFAULT_ACTIVE_STEP_MS = 25;

export function systemCatalog(catalog: TieCatalog | null | undefined, system: SystemType): TieSystemCatalog | null {
  return catalog?.systems?.[system] ?? null;
}

export function stepColor(delayMs: number, nominals: readonly number[]): string {
  const index = nominals.findIndex((value) => Math.abs(value - delayMs) < 1e-6);
  return index < 0 ? OFF_NOMINAL_COLOR : STEP_COLORS[index % STEP_COLORS.length];
}

function positive(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) && value > 0 ? value : null;
}

/** Активная ступень при открытии режима: магистраль сети, иначе 25 мс. */
export function defaultActiveStep(network: InitiationNetwork): number {
  return positive(network.timing_params?.trunk_ms) ?? DEFAULT_ACTIVE_STEP_MS;
}

/** Активное замедление в скважине: из параметров сети, иначе умолчание системы. */
export function defaultDownhole(network: InitiationNetwork, system: TieSystemCatalog): number {
  const value = network.timing_params?.downhole_delay_ms;
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : system.downhole_default_ms;
}

/** Ближайший номинал (как `design/timing.py::_snap`: при равенстве — меньший). */
export function nearestNominal(value: number, options: readonly number[]): number {
  return options.reduce((best, option) => (Math.abs(option - value) < Math.abs(best - value) ? option : best));
}

/** Инструменты правки коммутации на плане. */
export type TieTool = "tie" | "step" | "starter" | "downhole";

export const TIE_TOOLS: { id: TieTool; label: string; key: string; title: string }[] = [
  { id: "tie", label: "Связь", key: "T", title: "Связь (T): протянуть мышь через скважины — цепочка; клик по двум скважинам — одна связь" },
  { id: "step", label: "Ступень", key: "D", title: "Ступень (D): клик или рамка по линиям — активный номинал" },
  { id: "starter", label: "Стартер", key: "S", title: "Стартер (S): клик по скважине ставит или снимает стартер" },
  { id: "downhole", label: "В скважине", key: "H", title: "В скважине (H): клик или рамка по скважинам — замедление в скважине" },
];

const TOOL_KEYS: Record<string, TieTool> = { t: "tie", "е": "tie", d: "step", "в": "step", s: "starter", "ы": "starter", h: "downhole", "р": "downhole" };

/** Инструмент по клавише (латиница и русская раскладка). */
export function tieToolForKey(key: string): TieTool | null {
  return TOOL_KEYS[key.toLowerCase()] ?? null;
}

/** Номинал по цифре 1–5 (по порядку палитры). */
export function nominalForKey(key: string, nominals: readonly number[]): number | null {
  if (!/^[1-9]$/.test(key)) return null;
  return nominals[Number(key) - 1] ?? null;
}
