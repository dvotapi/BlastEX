// Состояние шага «Контур» (TASK-013, PR 2): выбранный способ, его входные
// данные и запрос предпросмотра. Только чистые функции — их проверяют тесты
// без DOM, а `ContourStep` лишь показывает состояние и зовёт их.
import type {
  CadAreaBasis,
  CadContourLines,
  CadContourMethod,
  CadContourRequest,
  CadContourResult,
  CadCrestSide,
  CadEntity,
  CadRoleCode,
  CadSource,
} from "../../../types/cad";
import type { CadContourItem } from "../../../types/design";
import { pieceAt, polylineXY, projectOnPolyline, type Snap, type XY } from "./contourGeometry";

export type AssemblyTool = "piece" | "points" | "segment";
export type WidthMode = "meters" | "rows";

export type ContourState = {
  method: CadContourMethod;
  /** «Готовый»: выбранная замкнутая линия. */
  handle: string;
  /** «Щелчок внутри»: точка щелчка. */
  point: XY | null;
  /** Роли линий, из которых строится контур щелчком и сборкой. */
  roles: CadRoleCode[];
  tolerance: string;
  bridge: string;
  /** «Сборка»: участки по порядку. */
  items: CadContourItem[];
  tool: AssemblyTool;
  /** Первый щелчок инструмента из двух («По точкам», «Отрезок»). */
  pending: { point: XY; handle?: string; m?: number } | null;
  crestStart: XY | null;
  crestEnd: XY | null;
  widthMode: WidthMode;
  width: string;
  rows: string;
  side: CadCrestSide;
  /** Площадь с блоковой карты — для сверки S верх, S низ и S ср. */
  mapArea: string;
  /** Какая площадь — площадь блока (соглашение маркшейдера объекта). */
  areaBasis: CadAreaBasis;
  selected: number | null;
};

export type Pick = { world: XY; snap: Snap | null; handle: string | null };

export type PickContext = { entities: Map<string, CadEntity>; lines: CadContourLines | null };

export const DEFAULT_CONTOUR_ROLES: CadRoleCode[] = ["block_contour", "design_line", "crest_top"];
export const DEFAULT_TOLERANCE_M = 0.5;
export const DEFAULT_BRIDGE_M = 5;

export function parseNumber(text: string): number | null {
  const value = Number(text.replace(",", ".").trim());
  return text.trim() && Number.isFinite(value) ? value : null;
}

/** Линия замкнута или почти: разрыв концов не больше допуска — её замкнёт «Готовый». */
function closable(entity: CadEntity, tolerance: number): boolean {
  if (entity.geometry_type !== "line" || entity.points.length < 3) return false;
  if (entity.closed || entity.closed_by_gap) return true;
  const first = entity.points[0];
  const last = entity.points[entity.points.length - 1];
  return Math.hypot(last[0] - first[0], last[1] - first[1]) <= tolerance;
}

/** Замкнутые линии для «Готового»: сначала контуры блока, затем по площади. */
export function readyCandidates(entities: CadEntity[], tolerance = DEFAULT_TOLERANCE_M): CadEntity[] {
  return entities
    .filter((entity) => closable(entity, tolerance))
    .sort(
      (a, b) =>
        Number(b.role === "block_contour") - Number(a.role === "block_contour") || b.area_m2 - a.area_m2,
    );
}

export function initialContour(source: CadSource): ContourState {
  const ready = readyCandidates(source.entities).find((entity) => entity.role === "block_contour");
  return {
    method: ready ? "ready" : "assembly",
    handle: ready?.handle ?? "",
    point: null,
    roles: [...DEFAULT_CONTOUR_ROLES],
    tolerance: String(DEFAULT_TOLERANCE_M),
    bridge: String(DEFAULT_BRIDGE_M),
    items: [],
    tool: "piece",
    pending: null,
    crestStart: null,
    crestEnd: null,
    widthMode: "meters",
    width: "20",
    rows: "5",
    side: "auto",
    mapArea: "",
    areaBasis: source.area_basis ?? "mean",
    selected: null,
  };
}

/** Площадь блока выбранным способом: S верх, S низ или S ср. */
export function blockArea(result: CadContourResult | null, basis: CadAreaBasis): number | null {
  if (!result?.top) return null;
  if (basis === "top") return result.top.area_m2;
  if (basis === "bottom") return result.bottom?.area_m2 ?? null;
  return result.mean_area_m2;
}

/** Ширина блока по бровке в метрах: число или «рядов × W» (W — между рядами из паспорта). */
export function widthMeters(state: ContourState, burden: number | null): number | null {
  if (state.widthMode === "meters") {
    const width = parseNumber(state.width);
    return width !== null && width > 0 ? width : null;
  }
  const rows = parseNumber(state.rows);
  return rows !== null && rows > 0 && burden !== null && burden > 0 ? rows * burden : null;
}

export function toleranceOf(state: ContourState): number {
  const value = parseNumber(state.tolerance);
  return value !== null && value > 0 ? value : DEFAULT_TOLERANCE_M;
}

export function contourRequest(state: ContourState, burden: number | null): CadContourRequest | null {
  const tolerance_m = toleranceOf(state);
  switch (state.method) {
    case "ready":
      return state.handle ? { method: "ready", handle: state.handle, tolerance_m } : null;
    case "click": {
      if (!state.point) return null;
      const bridge = parseNumber(state.bridge);
      return {
        method: "click",
        point: state.point,
        roles: state.roles,
        tolerance_m,
        bridge_m: bridge !== null && bridge >= 0 ? bridge : DEFAULT_BRIDGE_M,
      };
    }
    case "assembly":
      return state.items.length ? { method: "assembly", items: state.items, tolerance_m } : null;
    case "crest": {
      const width_m = widthMeters(state, burden);
      if (!state.crestStart || !state.crestEnd || width_m === null) return null;
      return { method: "crest", crest: { start: state.crestStart, end: state.crestEnd, width_m, side: state.side }, tolerance_m };
    }
  }
}

function part(handle: string, start_m: number, end_m: number): CadContourItem {
  return { kind: "part", handle, start_m, end_m, points: [], flip: false, label: "" };
}

function withItem(state: ContourState, item: CadContourItem): ContourState {
  return { ...state, items: [...state.items, item], pending: null, selected: state.items.length };
}

/** Щелчок по чертежу на шаге «Контур» — по правилам текущего способа и инструмента. */
export function applyPick(state: ContourState, pick: Pick, context: PickContext): ContourState {
  const at = pick.snap?.point ?? pick.world;
  const handle = pick.snap?.handle ?? pick.handle;
  const entity = handle ? context.entities.get(handle) : undefined;
  const line = entity && entity.geometry_type === "line" && entity.points.length > 1 ? entity : undefined;

  switch (state.method) {
    case "ready":
      return line && closable(line, toleranceOf(state)) ? { ...state, handle: line.handle } : state;
    case "click":
      return { ...state, point: pick.world };
    case "crest": {
      const crests = context.lines?.crests_top ?? [];
      let best: { point: XY; distance: number } | null = null;
      for (const crest of crests) {
        const hit = projectOnPolyline(crest.points.map(([x, y]) => [x, y] as XY), pick.world);
        if (!best || hit.distance < best.distance) best = hit;
      }
      if (!best) return state;
      if (!state.crestStart || state.crestEnd) return { ...state, crestStart: best.point, crestEnd: null };
      return { ...state, crestEnd: best.point };
    }
    case "assembly": {
      if (state.tool === "segment") {
        if (!state.pending) return { ...state, pending: { point: at } };
        return withItem(state, { kind: "segment", handle: "", start_m: 0, end_m: 0, points: [state.pending.point, at], flip: false, label: "" });
      }
      if (!line) return state;
      if (state.tool === "piece") {
        // Кусок выбирает сам курсор, а не привязка: привязка к узлу дала бы
        // m ровно на разрезе, и добавился бы кусок за узлом.
        const raw = projectOnPolyline(polylineXY(line), pick.world).m;
        const piece = pieceAt(line, raw, context.lines?.splits[line.handle]);
        return withItem(state, part(line.handle, piece.start_m, piece.end_m));
      }
      const m = pick.snap?.handle === line.handle && pick.snap.m !== undefined ? pick.snap.m : projectOnPolyline(polylineXY(line), at).m;
      if (state.pending?.handle === line.handle && state.pending.m !== undefined) {
        return withItem(state, part(line.handle, Math.min(state.pending.m, m), Math.max(state.pending.m, m)));
      }
      return { ...state, pending: { point: at, handle: line.handle, m } };
    }
  }
}

export function undoItem(state: ContourState): ContourState {
  if (state.pending) return { ...state, pending: null };
  return { ...state, items: state.items.slice(0, -1), selected: null };
}

export function removeItem(state: ContourState, index: number): ContourState {
  return { ...state, items: state.items.filter((_, at) => at !== index), selected: null };
}

export function flipItem(state: ContourState, index: number): ContourState {
  return { ...state, items: state.items.map((item, at) => (at === index ? { ...item, flip: !item.flip } : item)) };
}

/** Результат любого способа — дальше правится как сборка (§2 «Блок по бровке», п. 3). */
export function asAssembly(state: ContourState, result: CadContourResult): ContourState {
  return { ...state, method: "assembly", items: result.items.map((item) => ({ ...item })), selected: null, pending: null };
}
