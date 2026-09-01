import type { Hole, HoleLoad, InitiationNetwork, ValidationWarning } from "../../types/design";
import { networkTies } from "../../types/design";

export type HoleHealthCode =
  | "ok"
  | "disabled"
  | "warning"
  | "error"
  | "no_charge"
  | "no_tie"
  | "timing_issue";

export type HoleHealth = {
  holeId: string;
  code: HoleHealthCode;
  /** 0 — норма, 1 — замечание, 2 — ошибка. */
  severity: 0 | 1 | 2;
  messages: string[];
};

export type HoleHealthContext = {
  loadsById?: Record<string, HoleLoad>;
  warnings?: ValidationWarning[];
  network?: InitiationNetwork | null;
  timesMs?: Record<string, number> | null;
  requireCharge?: boolean;
  requireNetwork?: boolean;
};

const TIMING_WARNING_CODES = new Set([
  "unconnected_holes",
  "hole_disconnected",
  "duplicate_times",
  "unexpected_firing_order",
  "high_mic",
  "insufficient_delays",
  "relief_direction",
  "isolated_network_branches",
]);

export function computeHoleHealth(hole: Hole, ctx: HoleHealthContext = {}): HoleHealth {
  const messages: string[] = [];
  let severity: 0 | 1 | 2 = 0;
  let code: HoleHealthCode = "ok";

  function bump(nextCode: HoleHealthCode, nextSeverity: 0 | 1 | 2, message: string) {
    messages.push(message);
    if (nextSeverity > severity) {
      severity = nextSeverity;
      code = nextCode;
    }
  }

  if (!hole.enabled) {
    return { holeId: hole.id, code: "disabled", severity: 0, messages: ["Скважина исключена из расчёта"] };
  }

  const load = ctx.loadsById?.[hole.id];
  if (ctx.requireCharge && (!load || load.total_charge_kg <= 0)) {
    bump("no_charge", 2, "Нет заряда");
  } else if (load && load.total_charge_kg <= 0) {
    bump("no_charge", 1, "Заряд не рассчитан");
  }

  if (ctx.requireNetwork && ctx.network) {
    const connected = isHoleConnected(hole.id, ctx.network);
    if (!connected) bump("no_tie", 2, "Нет связи в сети инициирования");
  }

  if (ctx.timesMs && hole.id in ctx.timesMs === false && ctx.requireNetwork) {
    bump("timing_issue", 1, "Нет времени воспламенения");
  }

  for (const warning of ctx.warnings ?? []) {
    if (warning.hole_id && warning.hole_id !== hole.id) continue;
    const level: 0 | 1 | 2 = TIMING_WARNING_CODES.has(warning.code) ? 1 : 2;
    bump(level === 2 ? "error" : "timing_issue", level, warning.message);
  }

  if (severity === 0) {
    return { holeId: hole.id, code: "ok", severity: 0, messages: [] };
  }
  if (severity === 1 && code === "ok") code = "warning";
  return { holeId: hole.id, code, severity, messages };
}

export function computeAllHoleHealth(holes: Hole[], ctx: HoleHealthContext = {}): Record<string, HoleHealth> {
  const result: Record<string, HoleHealth> = {};
  for (const hole of holes) {
    result[hole.id] = computeHoleHealth(hole, ctx);
  }
  return result;
}

export function summarizeHealth(all: Record<string, HoleHealth>): {
  total: number;
  ok: number;
  warning: number;
  error: number;
  disabled: number;
} {
  let ok = 0;
  let warning = 0;
  let error = 0;
  let disabled = 0;
  for (const item of Object.values(all)) {
    if (item.code === "disabled") disabled += 1;
    else if (item.severity >= 2) error += 1;
    else if (item.severity === 1) warning += 1;
    else ok += 1;
  }
  return { total: Object.keys(all).length, ok, warning, error, disabled };
}

export function healthColor(code: HoleHealthCode, severity: 0 | 1 | 2): string {
  if (code === "disabled") return "#a8b4ae";
  if (severity >= 2) return "#c0392b";
  if (severity === 1) return "#d68910";
  return "#2d7556";
}

function isHoleConnected(holeId: string, network: InitiationNetwork): boolean {
  if (network.starters?.includes(holeId)) return true;
  if (network.starter_items?.some((item) => item.hole_id === holeId)) return true;
  for (const tie of networkTies(network)) {
    if (tie.from_hole === holeId || tie.to_hole === holeId) return true;
  }
  for (const cord of network.detonating_cords ?? []) {
    if (cord.hole_ids.includes(holeId)) return true;
  }
  return false;
}
