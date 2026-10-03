// Состояние шагов «Поверхность» и «Итог» (TASK-013, PR 3): роли линий в
// кровле, исключённые отметки, подошва, подтверждение высоты и объём с
// блоковой карты. Только чистые функции — их проверяют тесты без DOM.
import { ruNumber } from "../../../lib/format";
import { plural } from "../../../lib/plural";
import type { CadContourResult, CadCrs, CadSource, CadSurfaceRequest, CadSurfaceResult, CadSurfaceRole } from "../../../types/cad";
import { emptyCoordinateSystem, type BlastDesign, type SurfaceModel } from "../../../types/design";
import { parseNumber } from "./contourState";

export type SurfaceState = {
  roles: CadSurfaceRole[];
  /** Исключённые отметки: id точки или «handle:вершина» линии съёмки. */
  excluded: string[];
  /** Проектная подошва; пустое поле — отметка подошвы шага «Контур». */
  floor: string;
  /** Какую высоту уступа вне 2–25 м подтвердил инженер: другая высота требует подтверждения заново. */
  confirmHeight: number | null;
  /** Объём с блоковой карты — для сверки. */
  mapVolume: string;
};

/** Роли линий в кровле и как каждая входит (§2 «Поверхность и подошва»). */
export const SURFACE_ROLES: Array<{ code: CadSurfaceRole; hint: string }> = [
  { code: "crest_top", hint: "жёсткий ограничитель, вершины через 1 м" },
  { code: "crest_bottom", hint: "жёсткий ограничитель, вершины через 1 м" },
  { code: "feature_line", hint: "ограничитель; без Z — отметка с поверхности" },
  { code: "contour_line", hint: "точки через 2 м и мягкий ограничитель" },
  { code: "spot_heights", hint: "массовые точки: точки, знаки, вершины съёмки" },
];

// Поле подошвы пустое и при явной подошве разбора: подошва контура и так её
// берёт и следует за полем шага «Слои», а скопированное значение отстало бы.
export function initialSurface(_source: CadSource): SurfaceState {
  return {
    roles: SURFACE_ROLES.map((role) => role.code),
    excluded: [],
    floor: "",
    confirmHeight: null,
    mapVolume: "",
  };
}

/** Подтверждена именно эта высота уступа (с точностью 5 см). */
export function heightConfirmed(state: SurfaceState, height: number | null): boolean {
  return state.confirmHeight !== null && height !== null && Math.abs(state.confirmHeight - height) < 0.05;
}

/** Подошва для кровли: поле, иначе отметка подошвы контура (поле «Подошва», имя слоя или паспорт). */
export function surfaceFloor(state: SurfaceState, contour: CadContourResult | null): number | null {
  return parseNumber(state.floor) ?? contour?.bench.toe_z_m ?? null;
}

export function surfaceRequest(state: SurfaceState, contour: CadContourResult | null): CadSurfaceRequest | null {
  if (!contour?.ok || !contour.top) return null;
  return {
    top: contour.top.points,
    bottom: contour.bottom?.points ?? null,
    roles: state.roles,
    excluded: state.excluded,
    floor_z_m: surfaceFloor(state, contour),
    crest_z_m: contour.bench.crest_z_m,
  };
}

export function toggleSurfaceRole(state: SurfaceState, role: CadSurfaceRole): SurfaceState {
  const roles = state.roles.includes(role) ? state.roles.filter((item) => item !== role) : [...state.roles, role];
  return { ...state, roles };
}

export function excludePoint(state: SurfaceState, id: string): SurfaceState {
  return state.excluded.includes(id) ? state : { ...state, excluded: [...state.excluded, id] };
}

export function restorePoint(state: SurfaceState, id: string): SurfaceState {
  return { ...state, excluded: state.excluded.filter((item) => item !== id) };
}

/** Расхождение значения с картой, % (карта не задана — null). */
export function percentDiff(value: number | null | undefined, reference: number | null): number | null {
  if (value === null || value === undefined || reference === null || reference <= 0) return null;
  return ((value - reference) / reference) * 100;
}

/** Почему «Построить блок» неактивна по кровле (null — можно строить). */
export function buildBlocker(
  state: SurfaceState,
  contour: CadContourResult | null,
  surface: CadSurfaceResult | null,
  pending: boolean,
): string | null {
  if (!contour?.ok) return null;
  if (pending) return "Считаю кровлю…";
  if (!surface?.ok) return "Кровля не построена — шаг «Поверхность».";
  if (surface.bench.needs_confirmation && !heightConfirmed(state, surface.bench.mean_height_m)) {
    return "Подтвердите высоту уступа на шаге «Итог».";
  }
  return null;
}

/** Кровля для паспорта: TIN предпросмотра и определение из чертежа. */
export function roofSurface(result: CadSurfaceResult, source: CadSource, state: SurfaceState, builtAt: string): SurfaceModel {
  const { quality } = result;
  return {
    kind: "top",
    name: "Кровля из чертежа",
    source_format: "cad",
    source_name: source.file_name,
    created_at: builtAt,
    coordinate_system: emptyCoordinateSystem(),
    points: [],
    polylines: [],
    tin: {
      vertices: result.tin.vertices.map(([x, y, z]) => ({ x, y, z })),
      triangles: result.tin.triangles,
    },
    cad: {
      source_id: source.id,
      file_name: source.file_name,
      roles: state.roles,
      excluded: state.excluded,
      builder: result.builder,
      plane: result.plane,
      floor_z_m: result.bench.floor_z_m,
      quality: {
        spot_count: quality.spot_count,
        coverage_pct: quality.coverage_pct,
        max_gap_m: quality.max_gap_m,
        outlier_count: quality.outlier_count,
        conflict_count: quality.conflict_count,
      },
      built_at: builtAt,
    },
  };
}

/** Что сменит «Построить блок» в паспорте — текст подтверждения (null — терять нечего). */
/** «МСК-66 зона 1, высоты Балтийская 1977, EPSG 6838» — смена одних высот видна в тексте. */
function crsLabel(crs: { name: string; height_system?: string | null; epsg?: number | null }): string {
  const parts = [crs.name.trim()];
  if (crs.height_system?.trim()) parts.push(`высоты ${crs.height_system.trim()}`);
  if (crs.epsg) parts.push(`EPSG ${crs.epsg}`);
  return parts.join(", ");
}

export function buildConfirmText(design: BlastDesign, toe: number | null, crs: CadCrs | null = null): string | null {
  const changes: string[] = [];
  if (design.contour.vertices.length) changes.push("контур блока и отметки уступа заменятся контуром из чертежа");
  // Смену именованной СК паспорта называем; «local» нового паспорта — ожидаемая смена.
  const current = design.coordinate_system;
  const named = current.name.trim() !== "" && current.name.trim().toLowerCase() !== "local";
  const differs =
    crs !== null &&
    (crs.name !== current.name || crs.height_system !== (current.height_system ?? "") || crs.epsg !== current.epsg);
  if (named && differs && crs) changes.push(`система координат «${crsLabel(current)}» сменится на «${crsLabel(crs)}»`);
  const { top, floor } = design.surfaces;
  if (top) changes.push(`кровля «${top.name}» заменится кровлей из чертежа`);
  if (floor) {
    changes.push(`поверхность подошвы «${floor.name}» снимется: подошва — отметка ${toe === null ? "из чертежа" : `${ruNumber(toe, 1)} м`}`);
  }
  const count = design.holes.length;
  if (count) changes.push(`${count} ${plural(count, ["скважина", "скважины", "скважин"])}, заряды и сеть очистятся`);
  if (!changes.length) return null;
  return `«Построить блок» сменит паспорт:\n${changes.map((item) => `— ${item};`).join("\n")}\nПродолжить?`;
}
