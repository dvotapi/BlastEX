// Подложка ситуации карьера (TASK-013, PR 4): дороги, ЛЭП, склады, контур
// карьера — слоями и цветами из DXF. Здесь только чистая геометрия: штрихи
// плана в экранных координатах (рисует `SituationCanvas`) и линии 3D.
import { ruDate, ruDateTime } from "../../lib/format";
import type { Camera, Viewport } from "../../lib/geometry2d";
import type { CadSituationCatalogue, CadSituationGeometry } from "../../types/cad";

/** Цвет вместо белого (ACI 7) и почти белых: на светлом плане их не видно. */
export const SITUATION_LIGHT_REPLACEMENT = "#3a4540";
const SITUATION_DEFAULT_COLOR = "#6e7c75";
// Относительная яркость, выше которой цвет на фоне плана не читается.
const LIGHT_LUMINANCE = 0.85;

/** Версия серии на экране: геометрия источника и ключ его серии. */
export type SituationShown = { seriesKey: string; geometry: CadSituationGeometry };

export type SituationStroke = {
  key: string;
  color: string;
  /** Ломаные в экранных координатах: x0, y0, x1, y1, … */
  polylines: number[][];
  /** Точки: x0, y0, x1, y1, … */
  points: number[];
};

export type Situation3dLine = { color: string; points: Array<{ x: number; y: number; z: number }> };

/** Ключ слоя для флажков «Вида»: серия и имя слоя — смена даты версии флажки не сбрасывает. */
export function situationLayerKey(seriesKey: string, layerName: string): string {
  return `${seriesKey}\u0000${layerName}`;
}

function channel(value: number): number {
  const c = value / 255;
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

export function situationColor(hex: string | null): string {
  const match = /^#?([0-9a-f]{6})$/i.exec(hex ?? "");
  if (!match) return SITUATION_DEFAULT_COLOR;
  const value = parseInt(match[1], 16);
  const luminance =
    0.2126 * channel((value >> 16) & 255) + 0.7152 * channel((value >> 8) & 255) + 0.0722 * channel(value & 255);
  return luminance > LIGHT_LUMINANCE ? SITUATION_LIGHT_REPLACEMENT : `#${match[1].toLowerCase()}`;
}

/** Штрихи плана: по одному на видимый слой, в экранных координатах (как `worldToScreen`). */
export function situationStrokes(
  shown: SituationShown[],
  hidden: Set<string>,
  camera: Camera,
  viewport: Viewport,
): SituationStroke[] {
  const cx = viewport.width / 2;
  const cy = viewport.height / 2;
  const sx = (x: number) => cx + (x - camera.x) * camera.scale;
  const sy = (y: number) => cy - (y - camera.y) * camera.scale;
  const strokes: SituationStroke[] = [];
  for (const { seriesKey, geometry } of shown) {
    for (const layer of geometry.layers) {
      const key = situationLayerKey(seriesKey, layer.name);
      if (layer.omitted || hidden.has(key)) continue;
      const polylines = layer.lines.map((line) => {
        const flat: number[] = [];
        for (const [x, y] of line.points) flat.push(sx(x), sy(y));
        if (line.closed && line.points.length > 2) flat.push(flat[0], flat[1]);
        return flat;
      });
      const points: number[] = [];
      for (const [x, y] of layer.points) points.push(sx(x), sy(y));
      strokes.push({ key, color: situationColor(layer.color), polylines, points });
    }
  }
  return strokes;
}

/**
 * Линии ситуации для 3D. Линия без отметок (2D-чертёж, Z = 0) ложится на
 * отметку бровки паспорта: на нуле она ушла бы на сотни метров под блок.
 */
export function situation3dLines(shown: SituationShown[], hidden: Set<string>, crestZ: number): Situation3dLine[] {
  const lines: Situation3dLine[] = [];
  for (const { seriesKey, geometry } of shown) {
    for (const layer of geometry.layers) {
      if (layer.omitted || hidden.has(situationLayerKey(seriesKey, layer.name))) continue;
      const color = situationColor(layer.color);
      for (const line of layer.lines) {
        const flat = line.points.every(([, , z]) => Math.abs(z) < 1e-3);
        const points = line.points.map(([x, y, z]) => ({ x, y, z: flat ? crestZ : z }));
        if (line.closed && points.length > 2) points.push(points[0]);
        lines.push({ color, points });
      }
    }
  }
  return lines;
}


/** Серия ситуации в панели «Вид». `layers` = null — геометрия ещё грузится. */
export type SituationPanelSeries = {
  key: string;
  title: string;
  versions: Array<{ sourceId: string; label: string }>;
  displayedId: string;
  passportId: string | null;
  layers: Array<{ key: string; name: string; color: string; kindLabel: string; omitted: boolean }> | null;
};

/** Версия серии: дата съёмки, файл, время загрузки — у каталога и у источника окна. */
type VersionLike = { survey_date: string | null; file_name: string; uploaded_at: string };

/** Подписи версий — дата съёмки; одинаковые даты (повторная выгрузка) различает время загрузки. */
export function versionLabels(versions: VersionLike[]): string[] {
  const base = versions.map((item) => (item.survey_date ? ruDate(item.survey_date) : item.file_name));
  return versions.map((item, index) =>
    base.filter((label) => label === base[index]).length > 1
      ? `${base[index]} · загружен ${ruDateTime(item.uploaded_at)}`
      : base[index],
  );
}

/** Модель группы «Ситуация»: серии каталога, показанные версии и их слои. */
export function situationPanelSeries(
  catalogue: CadSituationCatalogue | null,
  shown: SituationShown[],
  displayed: Record<string, string>,
  passport: Record<string, string>,
): SituationPanelSeries[] {
  return (catalogue?.series ?? []).map((series) => {
    const displayedId = displayed[series.key] ?? series.default_source_id;
    const loaded = shown.find((item) => item.seriesKey === series.key && item.geometry.source_id === displayedId);
    return {
      key: series.key,
      title: series.title,
      versions: versionLabels(series.versions).map((label, index) => ({
        sourceId: series.versions[index].source_id,
        label,
      })),
      displayedId,
      passportId: passport[series.key] ?? null,
      layers: loaded
        ? loaded.geometry.layers.map((layer) => ({
            key: situationLayerKey(series.key, layer.name),
            name: layer.name,
            color: situationColor(layer.color),
            kindLabel: layer.kind_label,
            omitted: layer.omitted,
          }))
        : null,
    };
  });
}

/** Пачка отрезков 3D одного цвета: пары вершин (x, высота, −y) от общей точки отсчёта. */
export type SituationSegmentBatch = { color: string; positions: Float32Array };

/**
 * Линии ситуации 3D — по одной пачке отрезков на цвет (`THREE.LineSegments`):
 * тысячи полилиний карьера — несколько вызовов отрисовки, а не тысячи.
 * Координаты — от первой точки (float32 на МСК без потери точности); сцена
 * сдвигает группу целиком при смене центра.
 */
export function situationSegments(lines: Situation3dLine[]): {
  origin: { x: number; y: number; z: number } | null;
  batches: SituationSegmentBatch[];
} {
  const first = lines.find((line) => line.points.length >= 2)?.points[0];
  if (!first) return { origin: null, batches: [] };
  const origin = { x: first.x, y: first.y, z: first.z };
  const byColor = new Map<string, number[]>();
  for (const line of lines) {
    if (line.points.length < 2) continue;
    let target = byColor.get(line.color);
    if (!target) byColor.set(line.color, (target = []));
    for (let index = 1; index < line.points.length; index += 1) {
      const a = line.points[index - 1];
      const b = line.points[index];
      target.push(a.x - origin.x, a.z - origin.z, -(a.y - origin.y), b.x - origin.x, b.z - origin.z, -(b.y - origin.y));
    }
  }
  return {
    origin,
    batches: [...byColor.entries()].map(([color, positions]) => ({ color, positions: new Float32Array(positions) })),
  };
}
