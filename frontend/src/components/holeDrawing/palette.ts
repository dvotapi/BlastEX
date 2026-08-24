// Палитра чертежей скважины. Цвета ВВ совпадают с серверной схемой заряда
// (blast_hole_viz.py, CHARGE_COLORS), чтобы разрез в проекте и схема в расчёте
// показывали одно и то же ВВ одинаково.

export const DRAW = {
  rock: "#e8ece9",
  rockLine: "#b8c4bd",
  benchLine: "#94a49b",
  barrelWall: "#7d8c84",
  barrelVoid: "#f7f9f8",
  subdrill: "#c9d3cd",
  stemming: "#a9835a",
  stemmingDark: "#8a6742",
  air: "#8fb7d9",
  primer: "#e4b94f",
  primerEdge: "#173125",
  nsi: "#2d7556",
  dimension: "#2d7556",
  text: "#3b4b43",
  textMuted: "#6f7d76",
  collar: "#2d7556",
  accent: "#e5b94c",
} as const;

const EXPLOSIVE_COLORS: [string, string][] = [
  ["Гранулит", "#efe3c4"],
  ["ЭВЕРСИН", "#d0483c"],
  ["Э-100", "#d0483c"],
  ["Эмул", "#d97b45"],
  ["Игдан", "#c9a227"],
  ["АНФО", "#c9a227"],
  ["ANFO", "#c9a227"],
];

const DEFAULT_EXPLOSIVE_COLOR = "#4472C4";

/** Цвет колонны заряда по названию/метке ВВ. */
export function explosiveColor(...names: (string | undefined)[]): string {
  const haystack = names.filter(Boolean).join(" ");
  for (const [key, color] of EXPLOSIVE_COLORS) {
    if (haystack.includes(key)) return color;
  }
  return DEFAULT_EXPLOSIVE_COLOR;
}

/** Тёмный вариант цвета заряда для обводки и разделителей дек. */
export function darken(hex: string, amount = 0.35): string {
  const value = hex.replace("#", "");
  const full = value.length === 3 ? value.split("").map((c) => c + c).join("") : value;
  const num = parseInt(full, 16);
  const r = Math.round(((num >> 16) & 255) * (1 - amount));
  const g = Math.round(((num >> 8) & 255) * (1 - amount));
  const b = Math.round((num & 255) * (1 - amount));
  return `#${((1 << 24) | (r << 16) | (g << 8) | b).toString(16).slice(1)}`;
}
