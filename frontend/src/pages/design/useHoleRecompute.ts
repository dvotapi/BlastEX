// Автопересчёт скважин на странице «Проектирование» (TASK-013, PR 3).
//
// При изменении кровли, подошвы, перебура скважин или сетки сервер ставит
// устья на кровлю и считает длины до подошвы с перебуром (`/design/holes/
// recompute`). Запрос уходит через 300 мс после последнего изменения,
// устаревший ответ отбрасывается. Ответ применяется действием
// `RECOMPUTE_HOLES` вне истории отмены: отмена правки сама вызывает пересчёт.
//
// Открытие паспорта скважины не меняет: первый ответ после загрузки даёт
// только флаги, объём и погонаж. Утверждённый паспорт (`apply` = false) тоже
// только читается.
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../api/endpoints";
import { angleAzimuth, holeLength } from "../../lib/geometry2d";
import type { BlastDesign, HoleRecomputeFlag, HoleRecomputeResponse } from "../../types/design";
import type { DesignAction } from "./designReducer";

export const RECOMPUTE_DELAY_MS = 300;

type Fetcher = (payload: Parameters<typeof api.design.recomputeHoles>[0]) => Promise<HoleRecomputeResponse>;

export type HoleRecomputeView = {
  flags: Record<string, HoleRecomputeFlag[]>;
  blockVolumeM3: number | null;
  drillingM: number | null;
  meanHeightM: number | null;
  pending: boolean;
  error: string;
};

const EMPTY: HoleRecomputeView = { flags: {}, blockVolumeM3: null, drillingM: null, meanHeightM: null, pending: false, error: "" };

// Параметры сетки, задающие свою глубину видов скважин (как в `hole_recompute.explicit_depth_m`).
const DEPTH_PARAMS = ["depth_m", "stab_depth_m", "contour_depth_m", "presplit_depth_m", "trim_depth_m", "satellite_depth_m"];

function round(value: number, digits: number): number {
  const scale = 10 ** digits;
  return Math.round(value * scale) / scale;
}

/**
 * Всё, от чего зависит пересчёт, — и ничего из того, что он сам меняет:
 * отметка устья и забой входят, только когда их задали руками.
 */
export function recomputeKey(design: BlastDesign, params: Record<string, unknown>): string {
  const top = design.surfaces.top;
  const { bench } = design.contour;
  return JSON.stringify({
    roof: top ? [top.name, top.created_at, top.tin.vertices.length, top.tin.triangles.length] : null,
    floor: design.surfaces.floor ? [design.surfaces.floor.created_at, design.surfaces.floor.tin.vertices.length] : null,
    bench: [bench.crest_z_m, bench.toe_z_m],
    contour: design.contour.vertices.map((vertex) => [round(vertex.x, 3), round(vertex.y, 3)]),
    cad: design.contour.cad ? [design.contour.cad.edited, design.contour.cad.bottom?.length ?? 0] : null,
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
        hole.enabled,
        manual,
        manual.includes("collar_z") ? hole.collar.z : null,
        manual.includes("length") ? round(holeLength(hole.collar, hole.toe), 4) : null,
        round(angleDeg, 3),
        round(azimuthDeg, 3),
      ];
    }),
  });
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
  // Ключ паспорта на момент загрузки: пока он не сменился, скважины не трогаем.
  const identity = `${design.design_id}|${design.updated_at}|${design.revision}`;
  const baseline = useRef({ identity, key });
  if (baseline.current.identity !== identity) baseline.current = { identity, key };
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
    const applyHoles = apply && key !== baseline.current.key;
    setView((previous) => ({ ...previous, pending: true }));
    const timer = window.setTimeout(() => {
      fetcher({ holes: current.holes, contour: current.contour, surfaces: current.surfaces, params: latestParams.current })
        .then((response) => {
          if (number !== sequence.current) return;
          setView({
            flags: response.flags,
            blockVolumeM3: response.block_volume_m3,
            drillingM: response.drilling_m,
            meanHeightM: response.mean_height_m,
            pending: false,
            error: "",
          });
          if (applyHoles) dispatch({ type: "RECOMPUTE_HOLES", holes: response.holes });
        })
        .catch((reason) => {
          if (number !== sequence.current) return;
          setView((previous) => ({
            ...previous,
            pending: false,
            error: reason instanceof Error ? reason.message : "Не удалось пересчитать скважины.",
          }));
        });
    }, RECOMPUTE_DELAY_MS);
    return () => window.clearTimeout(timer);
    // Пересчёт — по содержимому (`key`), а не по каждому новому объекту паспорта.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, apply]);

  return view;
}
