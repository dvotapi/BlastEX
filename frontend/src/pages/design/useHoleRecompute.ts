// Автопересчёт скважин на странице «Проектирование» (TASK-013, PR 3).
//
// При изменении кровли, подошвы, перебура скважин или сетки сервер ставит
// устья на кровлю и считает длины до подошвы с перебуром (`/design/holes/
// recompute`). Запрос уходит через 300 мс после последнего изменения,
// устаревший ответ отбрасывается. Ответ применяется действием
// `RECOMPUTE_HOLES` вне истории отмены: отмена правки сама вызывает пересчёт.
//
// Скважины меняются только по триггерам плана (кровля, подошва, перебур,
// сетка — `applyKey`): открытие паспорта, включение скважины и правка контура
// дают только флаги и объём. Утверждённый паспорт (`apply` = false) только
// читается. Если пересчёт сменил длины при зарядах или геологии — заметка.
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../api/endpoints";
import { ruNumber } from "../../lib/format";
import { angleAzimuth, holeLength } from "../../lib/geometry2d";
import { plural } from "../../lib/plural";
import type { BlastDesign, Hole, HoleRecomputeFlag, HoleRecomputeResponse, TIN } from "../../types/design";
import type { DesignAction } from "./designReducer";

export const RECOMPUTE_DELAY_MS = 300;

type Fetcher = (payload: Parameters<typeof api.design.recomputeHoles>[0]) => Promise<HoleRecomputeResponse>;

export type HoleRecomputeView = {
  flags: Record<string, HoleRecomputeFlag[]>;
  blockVolumeM3: number | null;
  meanHeightM: number | null;
  pending: boolean;
  error: string;
  /** Что сменил последний применённый пересчёт, если пора пересчитать заряды и геологию. */
  notice: string;
};

const EMPTY: HoleRecomputeView = { flags: {}, blockVolumeM3: null, meanHeightM: null, pending: false, error: "", notice: "" };

// Параметры сетки, задающие свою глубину видов скважин (как в `hole_recompute.explicit_depth_m`).
const DEPTH_PARAMS = ["depth_m", "stab_depth_m", "contour_depth_m", "presplit_depth_m", "trim_depth_m", "satellite_depth_m"];

function round(value: number, digits: number): number {
  const scale = 10 ** digits;
  return Math.round(value * scale) / scale;
}

// Отпечаток TIN по содержимому (вершины до 1 мм и треугольники): время и
// число вершин не отличают поверхность, заменённую в ту же секунду. Кэш по
// объекту — правки, не трогающие поверхность, отпечаток не пересчитывают.
const tinFingerprints = new WeakMap<TIN, string>();

export function tinFingerprint(tin: TIN): string {
  const cached = tinFingerprints.get(tin);
  if (cached !== undefined) return cached;
  let h1 = 0xdeadbeef ^ tin.vertices.length;
  let h2 = 0x41c6ce57 ^ tin.triangles.length;
  const mix = (value: number) => {
    h1 = Math.imul(h1 ^ value, 2654435761);
    h2 = Math.imul(h2 ^ value, 1597334677);
  };
  for (const vertex of tin.vertices) {
    mix(Math.round(vertex.x * 1000) | 0);
    mix(Math.round(vertex.y * 1000) | 0);
    mix(Math.round(vertex.z * 1000) | 0);
  }
  for (const triangle of tin.triangles) for (const index of triangle) mix(index);
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
  const value = `${tin.vertices.length}:${tin.triangles.length}:${(h2 >>> 0).toString(36)}${(h1 >>> 0).toString(36)}`;
  tinFingerprints.set(tin, value);
  return value;
}

/**
 * Триггеры пересчёта скважин (план, задача 12): кровля, подошва, перебур и
 * сетка — положение, вид, ось, ручные пометки, параметры глубины. Того, что
 * пересчёт меняет сам (отметка устья, забой), здесь нет, кроме заданного руками.
 */
export function applyKey(design: BlastDesign, params: Record<string, unknown>): string {
  const top = design.surfaces.top;
  const { bench } = design.contour;
  return JSON.stringify({
    roof: top ? tinFingerprint(top.tin) : null,
    floor: design.surfaces.floor ? tinFingerprint(design.surfaces.floor.tin) : null,
    bench: [bench.crest_z_m, bench.toe_z_m],
    depth: DEPTH_PARAMS.map((name) => params[name] ?? null),
    holes: design.holes.map((hole) => {
      const manual = hole.manual ?? [];
      const { angleDeg, azimuthDeg } = angleAzimuth(hole.collar, hole.toe);
      return [
        hole.id,
        round(hole.collar.x, 4),
        round(hole.collar.y, 4),
        hole.subdrill_m,
        hole.kind,
        manual,
        manual.includes("collar_z") ? hole.collar.z : null,
        manual.includes("length") ? round(holeLength(hole.collar, hole.toe), 4) : null,
        round(angleDeg, 3),
        round(azimuthDeg, 3),
      ];
    }),
  });
}

/** Всё, от чего зависят ответ пересчёта (флаги, объём): триггеры и ещё включение скважин и контур. */
export function recomputeKey(design: BlastDesign, params: Record<string, unknown>): string {
  return JSON.stringify({
    apply: applyKey(design, params),
    enabled: design.holes.map((hole) => hole.enabled),
    contour: design.contour.vertices.map((vertex) => [round(vertex.x, 3), round(vertex.y, 3)]),
    cad: design.contour.cad ? [design.contour.cad.edited, design.contour.cad.bottom?.length ?? 0] : null,
  });
}

/** Заметка о пересчёте, после которого заряды и геология отстали от новых длин. */
function changeNotice(design: BlastDesign, holes: Hole[]): string {
  const before = new Map(design.holes.map((hole) => [hole.id, hole]));
  let count = 0;
  let delta = 0;
  let stale = design.loads.length > 0;
  for (const hole of holes) {
    const old = before.get(hole.id);
    if (!old) continue;
    const change = holeLength(hole.collar, hole.toe) - holeLength(old.collar, old.toe);
    if (Math.abs(change) < 1e-6 && Math.abs(hole.collar.z - old.collar.z) < 1e-6) continue;
    count += 1;
    if (old.enabled) delta += change;
    stale ||= (old.intervals?.length ?? 0) > 0;
  }
  if (!count || !stale) return "";
  return (
    `Пересчитано по кровле и подошве: ${count} ${plural(count, ["скважина", "скважины", "скважин"])}, ` +
    `погонаж ${delta >= 0 ? "+" : "−"}${ruNumber(Math.abs(delta), 1)} м — пересчитайте заряды и геологию.`
  );
}

export function useHoleRecompute(
  design: BlastDesign,
  params: Record<string, unknown>,
  options: { apply: boolean; dispatch: (action: DesignAction) => void; fetcher?: Fetcher },
): HoleRecomputeView {
  const { apply, dispatch, fetcher = api.design.recomputeHoles } = options;
  const [view, setView] = useState<HoleRecomputeView>(EMPTY);
  const sequence = useRef(0);
  const key = useMemo(() => recomputeKey(design, params), [design, params]);
  // Триггеры, под которые посчитаны скважины: при загрузке паспорта — его
  // собственные, дальше — последнего применённого пересчёта. Пока они не
  // сменились, скважины не трогаем — открытие, включение скважины или правка
  // контура только читают; вернули подошву назад — пересчёт снова.
  const identity = `${design.design_id}|${design.updated_at}|${design.revision}`;
  const triggers = useMemo(() => applyKey(design, params), [design, params]);
  const applied = useRef({ identity, triggers });
  if (applied.current.identity !== identity) applied.current = { identity, triggers };
  // Заметка — своего паспорта и до пересчёта зарядов.
  const noticeOwner = useRef<{ identity: string; loads: BlastDesign["loads"] } | null>(null);
  const latest = useRef(design);
  latest.current = design;
  const latestParams = useRef(params);
  latestParams.current = params;

  useEffect(() => {
    const number = ++sequence.current;
    const current = latest.current;
    if (current.contour.vertices.length < 3) {
      setView(EMPTY);
      return;
    }
    const applyHoles = apply && triggers !== applied.current.triggers;
    const requested = { identity, triggers };
    setView((previous) => ({ ...previous, pending: true }));
    const timer = window.setTimeout(() => {
      fetcher({ holes: current.holes, contour: current.contour, surfaces: current.surfaces, params: latestParams.current })
        .then((response) => {
          if (number !== sequence.current) return;
          const notice = applyHoles ? changeNotice(current, response.holes) : "";
          if (notice) noticeOwner.current = { identity: requested.identity, loads: current.loads };
          setView((previous) => ({
            flags: response.flags,
            blockVolumeM3: response.block_volume_m3,
            meanHeightM: response.mean_height_m,
            pending: false,
            error: "",
            notice: notice || previous.notice,
          }));
          if (applyHoles) {
            applied.current = requested;
            dispatch({ type: "RECOMPUTE_HOLES", holes: response.holes });
          }
        })
        .catch((reason) => {
          if (number !== sequence.current) return;
          // Длины и объём уже не свежие: объём не показываем, ошибку — да.
          setView((previous) => ({
            ...previous,
            flags: {},
            blockVolumeM3: null,
            meanHeightM: null,
            pending: false,
            error: reason instanceof Error ? reason.message : "Не удалось пересчитать скважины.",
          }));
        });
    }, RECOMPUTE_DELAY_MS);
    return () => window.clearTimeout(timer);
    // Пересчёт — по содержимому (`key`), а не по каждому новому объекту паспорта.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, apply]);

  const owner = noticeOwner.current;
  const ownNotice = owner !== null && owner.identity === identity && owner.loads === design.loads;
  return ownNotice ? view : { ...view, notice: "" };
}
