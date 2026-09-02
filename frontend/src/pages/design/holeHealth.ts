import { holeLength } from "../../lib/geometry2d";
import type {
  AnalyzeResponse,
  AsDrilledHole,
  BlockContour,
  Hole,
  HoleLoad,
  InitiationNetwork,
  Point3,
  ValidationWarning,
} from "../../types/design";
import { networkTies } from "../../types/design";

export type HoleHealthCode =
  | "ok"
  | "unconnected"
  | "missing_primer"
  | "missing_charge"
  | "extra_hole"
  | "outside_contour"
  | "actual_unmatched";

export const HEALTH_LABELS: Record<HoleHealthCode, string> = {
  ok: "без замечаний",
  unconnected: "нет связи",
  missing_primer: "нет боевика",
  missing_charge: "нет заряда",
  extra_hole: "лишняя скважина",
  outside_contour: "вне контура",
  actual_unmatched: "факт без проекта",
};

export const HEALTH_COLORS: Record<HoleHealthCode, string> = {
  ok: "#2d7556",
  unconnected: "#d8455a",
  missing_primer: "#e07b2d",
  missing_charge: "#c43a5c",
  extra_hole: "#8a8f94",
  outside_contour: "#9b59b6",
  actual_unmatched: "#3d6ea8",
};

const WARNING_CODE_TO_HEALTH: Record<string, HoleHealthCode> = {
  unconnected_holes: "unconnected",
  hole_disconnected: "unconnected",
  missing_primer: "missing_primer",
  missing_charge: "missing_charge",
  no_charge: "missing_charge",
  no_primer: "missing_primer",
  extra_hole: "extra_hole",
  outside_contour: "outside_contour",
};

export type HoleHealthMap = Record<string, HoleHealthCode>;

export type HealthSummary = {
  byCode: Record<HoleHealthCode, string[]>;
  issueCount: number;
  issues: Array<{ holeId: string; code: HoleHealthCode; label: string }>;
};

function pointInPolygon(point: { x: number; y: number }, vertices: Point3[]): boolean {
  if (vertices.length < 3) return true;
  let inside = false;
  for (let i = 0, j = vertices.length - 1; i < vertices.length; j = i, i += 1) {
    const xi = vertices[i].x;
    const yi = vertices[i].y;
    const xj = vertices[j].x;
    const yj = vertices[j].y;
    const intersect = yi > point.y !== yj > point.y
      && point.x < ((xj - xi) * (point.y - yi)) / (yj - yi + 1e-12) + xi;
    if (intersect) inside = !inside;
  }
  return inside;
}

function connectedHoleIds(network: InitiationNetwork): Set<string> {
  const connected = new Set<string>();
  for (const tie of networkTies(network)) {
    connected.add(tie.from_hole);
    connected.add(tie.to_hole);
  }
  for (const cord of network.detonating_cords) {
    for (const id of cord.hole_ids) connected.add(id);
  }
  for (const ch of network.electronic_channels) connected.add(ch.hole_id);
  for (const id of Object.keys(network.electronic_times_ms ?? {})) connected.add(id);
  for (const item of network.starter_items) connected.add(item.hole_id);
  for (const id of network.starters) connected.add(id);
  return connected;
}

function hasNetwork(network: InitiationNetwork): boolean {
  return Boolean(
    network.connectors.length
    || network.surface_connectors.length
    || network.starters.length
    || network.starter_items.length
    || network.detonating_cords.length
    || network.electronic_channels.length
    || Object.keys(network.electronic_times_ms ?? {}).length,
  );
}

function warningsByHole(warnings: ValidationWarning[]): Map<string, HoleHealthCode> {
  const map = new Map<string, HoleHealthCode>();
  for (const warning of warnings) {
    const code = WARNING_CODE_TO_HEALTH[warning.code];
    if (!code || !warning.hole_id) continue;
    const prev = map.get(warning.hole_id);
    if (!prev || severity(code) > severity(prev)) map.set(warning.hole_id, code);
  }
  return map;
}

function severity(code: HoleHealthCode): number {
  switch (code) {
    case "unconnected": return 5;
    case "missing_charge": return 4;
    case "missing_primer": return 4;
    case "outside_contour": return 3;
    case "actual_unmatched": return 3;
    case "extra_hole": return 2;
    default: return 0;
  }
}

function pickWorst(current: HoleHealthCode, next: HoleHealthCode): HoleHealthCode {
  return severity(next) > severity(current) ? next : current;
}

export function computeHoleHealth(
  hole: Hole,
  context: {
    load?: HoleLoad;
    network: InitiationNetwork;
    timesMs?: Record<string, number> | null;
    warnings?: ValidationWarning[];
    contour: BlockContour;
    asDrilled?: AsDrilledHole[];
  },
): HoleHealthCode {
  let code: HoleHealthCode = "ok";

  if (!hole.enabled) return "extra_hole";

  const warningMap = warningsByHole(context.warnings ?? []);
  if (warningMap.has(hole.id)) return warningMap.get(hole.id)!;

  if (context.contour.vertices.length >= 3 && !pointInPolygon(hole.collar, context.contour.vertices)) {
    code = pickWorst(code, "outside_contour");
  }

  const load = context.load;
  const charged = (load?.total_charge_kg ?? 0) > 0;
  if (!charged && hole.kind === "production") {
    code = pickWorst(code, "missing_charge");
  }
  if (charged && (!load?.primers?.length && !(load?.primer_items?.length))) {
    code = pickWorst(code, "missing_primer");
  }

  if (hasNetwork(context.network)) {
    const connected = connectedHoleIds(context.network);
    const starters = new Set(
      context.network.starter_items.map((item) => item.hole_id).concat(context.network.starters),
    );
    if (!connected.has(hole.id) && starters.size > 0 && !starters.has(hole.id)) {
      code = pickWorst(code, "unconnected");
    } else if (!connected.has(hole.id) && context.timesMs && hole.id in context.timesMs) {
      code = pickWorst(code, "unconnected");
    }
  }

  return code;
}

export function computeAllHoleHealth(input: {
  holes: Hole[];
  loadsById: Record<string, HoleLoad>;
  network: InitiationNetwork;
  analysis?: AnalyzeResponse | null;
  contour: BlockContour;
  asDrilled?: AsDrilledHole[];
  designHoleIds?: Set<string>;
}): HoleHealthMap {
  const warnings = input.analysis?.validation_warnings ?? [];
  const timesMs = input.analysis?.times_ms ?? null;
  const map: HoleHealthMap = {};
  for (const hole of input.holes) {
    map[hole.id] = computeHoleHealth(hole, {
      load: input.loadsById[hole.id],
      network: input.network,
      timesMs,
      warnings,
      contour: input.contour,
      asDrilled: input.asDrilled,
    });
  }
  for (const item of input.asDrilled ?? []) {
    if (!input.designHoleIds?.has(item.design_hole_id) && item.design_hole_id) {
      map[`__actual__${item.design_hole_id}`] = "actual_unmatched";
    }
  }
  return map;
}

export function summarizeHealth(health: HoleHealthMap, holes: Hole[]): HealthSummary {
  const byCode = {
    ok: [] as string[],
    unconnected: [] as string[],
    missing_primer: [] as string[],
    missing_charge: [] as string[],
    extra_hole: [] as string[],
    outside_contour: [] as string[],
    actual_unmatched: [] as string[],
  };
  const holeIds = new Set(holes.map((h) => h.id));
  for (const [id, code] of Object.entries(health)) {
    if (id.startsWith("__actual__")) continue;
    if (!holeIds.has(id)) continue;
    byCode[code].push(id);
  }
  const issues = (Object.keys(byCode) as HoleHealthCode[])
    .filter((code) => code !== "ok")
    .flatMap((code) => byCode[code].map((holeId) => ({
      holeId,
      code,
      label: HEALTH_LABELS[code],
    })));
  for (const [id, code] of Object.entries(health)) {
    if (!id.startsWith("__actual__") || code !== "actual_unmatched") continue;
    const holeId = id.replace("__actual__", "");
    issues.push({ holeId, code, label: HEALTH_LABELS.actual_unmatched });
    byCode.actual_unmatched.push(holeId);
  }
  return {
    byCode,
    issueCount: issues.length,
    issues,
  };
}

export function healthColor(code: HoleHealthCode): string {
  return HEALTH_COLORS[code];
}

export function holeDepthM(hole: Hole): number {
  return holeLength(hole.collar, hole.toe);
}
