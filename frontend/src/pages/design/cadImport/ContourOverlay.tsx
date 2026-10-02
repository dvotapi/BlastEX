// Слой холста шага «Контур» (TASK-013, PR 2): контур по верхней бровке
// (заливка), по нижней (пунктир), свободная поверхность, замыкающие отрезки
// и мосты, продления флангов, разрывы бровок, точки щелчков и место ошибки.
import type { CadContourResult, CadGap } from "../../../types/cad";
import type { ScreenProjector } from "./CadCanvas";
import type { XY } from "./contourGeometry";

function path(points: number[][], toScreen: ScreenProjector, closed: boolean): string {
  const parts = points.map((point, index) => {
    const { x, y } = toScreen(point);
    return `${index ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`;
  });
  return parts.join("") + (closed && points.length > 2 ? "Z" : "");
}

/** Те же вершины — нижний контур не отличается от верхнего (подошвы нет или откос не учтён). */
function sameRing(a: number[][], b: number[][]): boolean {
  return a.length === b.length && a.every((point, index) => point[0] === b[index][0] && point[1] === b[index][1]);
}

export function ContourOverlay({
  toScreen,
  result,
  gaps,
  picks,
  selectedPath,
}: {
  toScreen: ScreenProjector;
  result: CadContourResult | null;
  gaps: CadGap[];
  /** Точки щелчков, ещё не ставшие контуром: первый щелчок, начало и конец по бровке. */
  picks: XY[];
  /** Участок сборки, выбранный в списке. */
  selectedPath: number[][] | null;
}) {
  const top = result?.top?.points ?? null;
  const bottom = result?.bottom?.points ?? null;
  // Сравнивается форма, а не площадь: подошва могла уйти наружу с одной
  // стороны и внутрь с другой при той же площади.
  const showBottom = Boolean(bottom && top && !sameRing(top, bottom));
  return (
    <>
      {showBottom && bottom && <path className="cad-contour-bottom" d={path(bottom, toScreen, true)} />}
      {top && (
        <path className={`cad-contour-top${result?.ok ? "" : " is-invalid"}`} d={path(top, toScreen, true)} />
      )}
      {top &&
        result?.free_faces.map(([a, b]) => (
          <path key={`free:${a}`} className="cad-free-face" d={path([top[a], top[b]], toScreen, false)} />
        ))}
      {result?.crest_line && <path className="cad-crest-chosen" d={path(result.crest_line, toScreen, false)} />}
      {result?.closings.map((closing, index) => (
        <path key={`closing:${index}`} className="cad-closing" d={path(closing, toScreen, false)} />
      ))}
      {result?.flanks.map((flank, index) =>
        flank.end ? <path key={`flank:${index}`} className="cad-flank" d={path([flank.start, flank.end], toScreen, false)} /> : null,
      )}
      {selectedPath && selectedPath.length > 1 && <path className="cad-item-selected" d={path(selectedPath, toScreen, false)} />}
      {gaps.map((gap, index) => {
        const a = toScreen(gap.a);
        const b = toScreen(gap.b);
        return (
          <g key={`gap:${index}`} className={`cad-gap reason-${gap.reason}`}>
            <title>{gap.reason === "gap" ? "Разрыв бровки — не сшит" : "Излом бровки — не сшит"}</title>
            <circle cx={a.x} cy={a.y} r={4} />
            <circle cx={b.x} cy={b.y} r={4} />
          </g>
        );
      })}
      {picks.map((point, index) => {
        const { x, y } = toScreen(point);
        return <circle key={`pick:${index}`} className="cad-pick-point" cx={x} cy={y} r={4} />;
      })}
      {result?.issues.map((issue, index) => {
        if (!issue.point) return null;
        const { x, y } = toScreen(issue.point);
        return (
          <g key={`issue:${index}`} className="cad-issue-point">
            <title>{issue.message}</title>
            <circle cx={x} cy={y} r={7} />
          </g>
        );
      })}
    </>
  );
}
