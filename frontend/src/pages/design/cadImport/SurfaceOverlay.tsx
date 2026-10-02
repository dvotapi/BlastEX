// Слой холста шагов «Поверхность» и «Итог» (TASK-013, PR 3): рёбра TIN кровли
// бледно, выбросы, исключённые отметки, конфликты отметок, возможные пороги
// и место, на которое наведена строка списка.
import { useMemo } from "react";
import type { CadSurfaceResult } from "../../../types/cad";
import type { ScreenProjector } from "./CadCanvas";
import type { SurfaceFocus } from "./SurfaceStep";

/** Рёбра TIN без повторов: общее ребро двух треугольников рисуется один раз. */
function tinEdges(triangles: number[][]): Array<[number, number]> {
  const seen = new Set<string>();
  const edges: Array<[number, number]> = [];
  for (const triangle of triangles) {
    for (let k = 0; k < 3; k += 1) {
      const a = triangle[k];
      const b = triangle[(k + 1) % 3];
      const key = a < b ? `${a}:${b}` : `${b}:${a}`;
      if (seen.has(key)) continue;
      seen.add(key);
      edges.push([a, b]);
    }
  }
  return edges;
}

function segmentPath(a: number[], b: number[], toScreen: ScreenProjector): string {
  const p = toScreen(a);
  const q = toScreen(b);
  return `M${p.x.toFixed(1)} ${p.y.toFixed(1)}L${q.x.toFixed(1)} ${q.y.toFixed(1)}`;
}

export function SurfaceOverlay({
  toScreen,
  result,
  focus,
}: {
  toScreen: ScreenProjector;
  result: CadSurfaceResult | null;
  focus: SurfaceFocus | null;
}) {
  const edges = useMemo(() => (result ? tinEdges(result.tin.triangles) : []), [result]);
  if (!result) return null;
  const vertices = result.tin.vertices;
  const tin = edges.map(([a, b]) => segmentPath(vertices[a], vertices[b], toScreen)).join("");
  const dot = (point: number[], className: string, radius: number, title: string, key: string) => {
    const { x, y } = toScreen(point);
    return (
      <circle key={key} className={className} cx={x} cy={y} r={radius}>
        <title>{title}</title>
      </circle>
    );
  };
  return (
    <>
      {tin && <path className="cad-tin" d={tin} />}
      {result.thresholds.map((item, index) => (
        <path
          key={`threshold:${index}`}
          className="cad-threshold"
          d={item.segments.map(([a, b]) => segmentPath(a, b, toScreen)).join("")}
        />
      ))}
      {result.conflicts.map((item, index) => dot(item.point, "cad-conflict", 5, "Конфликт отметок", `conflict:${index}`))}
      {result.excluded_points.map((item) => dot(item.point, "cad-excluded-point", 4, `Исключена: ${item.id}`, `excluded:${item.id}`))}
      {result.outliers.map((item) => dot(item.point, "cad-outlier", 5, `Выброс: ${item.id}`, `outlier:${item.id}`))}
      {focus && (
        <g className="cad-surface-focus">
          {focus.points.map((point, index) => {
            const { x, y } = toScreen(point);
            return <circle key={`focus:${index}`} cx={x} cy={y} r={10} />;
          })}
          {focus.segments.length > 0 && <path d={focus.segments.map(([a, b]) => segmentPath(a, b, toScreen)).join("")} />}
        </g>
      )}
    </>
  );
}
