import { useMemo, useState } from "react";
import { ruNumber } from "../../lib/format";
import type { DrawingPolyline, DrawingScan, Point3 } from "../../types/design";

type Role = "crest" | "toe";

const PREVIEW_W = 460;
const PREVIEW_H = 300;
const PREVIEW_PAD = 10;

const meanZ = (item: DrawingPolyline) => (item.z_min + item.z_max) / 2;

/**
 * Догадка о бровках среди самых длинных линий чертежа.
 *
 * Только по отметке выбирать нельзя: оси, рамки и подписи часто лежат на Z=0 и
 * оказываются «ниже» настоящей подошвы. Поэтому кандидаты сначала отбираются по
 * длине — бровка блока длиннее служебной графики, — и уже среди них берётся
 * самая высокая как верхняя и самая длинная из тех, что ниже её, как нижняя.
 * Ошибку инженер поправит одним кликом, но выбирать за него молча мы не вправе.
 */
export function guessBenchLines(polylines: DrawingPolyline[]): { crest: string; toe: string } {
  const candidates = [...polylines]
    .filter((item) => item.points.length >= 2)
    .sort((a, b) => b.length_m - a.length_m)
    .slice(0, 6);
  if (candidates.length < 2) return { crest: candidates[0]?.id ?? "", toe: "" };

  const crest = candidates.reduce((best, item) => (meanZ(item) > meanZ(best) ? item : best));
  const below = candidates.filter((item) => item.id !== crest.id && meanZ(item) < meanZ(crest));
  const toe = (below.length ? below : candidates.filter((item) => item.id !== crest.id))
    .reduce((best, item) => (item.length_m > best.length_m ? item : best));
  return { crest: crest.id, toe: toe.id };
}

function bounds(polylines: DrawingPolyline[]) {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const item of polylines) {
    for (const point of item.points) {
      minX = Math.min(minX, point.x);
      maxX = Math.max(maxX, point.x);
      minY = Math.min(minY, point.y);
      maxY = Math.max(maxY, point.y);
    }
  }
  if (!Number.isFinite(minX)) return { minX: 0, minY: 0, scale: 1, offsetX: 0, offsetY: 0 };
  const spanX = Math.max(maxX - minX, 1e-6);
  const spanY = Math.max(maxY - minY, 1e-6);
  const scale = Math.min((PREVIEW_W - PREVIEW_PAD * 2) / spanX, (PREVIEW_H - PREVIEW_PAD * 2) / spanY);
  return {
    minX,
    minY,
    scale,
    offsetX: (PREVIEW_W - spanX * scale) / 2,
    offsetY: (PREVIEW_H - spanY * scale) / 2,
  };
}

export function DrawingImportDialog({
  scan,
  busy,
  error,
  onCancel,
  onApply,
}: {
  scan: DrawingScan;
  busy: boolean;
  error: string;
  onCancel: () => void;
  onApply: (choice: { crest: DrawingPolyline; toe: DrawingPolyline }) => void;
}) {
  const guess = useMemo(() => guessBenchLines(scan.polylines), [scan.polylines]);
  const [crestId, setCrestId] = useState(guess.crest);
  const [toeId, setToeId] = useState(guess.toe);
  const [query, setQuery] = useState("");
  const [hoverId, setHoverId] = useState("");

  const view = useMemo(() => bounds(scan.polylines), [scan.polylines]);
  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return scan.polylines;
    return scan.polylines.filter((item) => item.layer.toLowerCase().includes(q) || item.entity.toLowerCase().includes(q));
  }, [scan.polylines, query]);

  const crest = scan.polylines.find((item) => item.id === crestId) ?? null;
  const toe = scan.polylines.find((item) => item.id === toeId) ?? null;
  const sameLine = Boolean(crestId) && crestId === toeId;

  function assign(role: Role, id: string) {
    if (role === "crest") {
      setCrestId(id);
      if (toeId === id) setToeId("");
    } else {
      setToeId(id);
      if (crestId === id) setCrestId("");
    }
  }

  function path(points: Point3[], closed: boolean): string {
    const d = points
      .map((point, index) => {
        const x = view.offsetX + (point.x - view.minX) * view.scale;
        // Y на карте растёт вверх, в SVG — вниз.
        const y = PREVIEW_H - (view.offsetY + (point.y - view.minY) * view.scale);
        return `${index === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
      })
      .join(" ");
    return closed ? `${d} Z` : d;
  }

  function roleOf(id: string): Role | "" {
    if (id === crestId) return "crest";
    if (id === toeId) return "toe";
    return "";
  }

  return (
    <div className="drawing-dialog-backdrop" role="presentation" onClick={onCancel}>
      <div className="drawing-dialog" role="dialog" aria-label="Выбор бровок из чертежа" onClick={(e) => e.stopPropagation()}>
        <header>
          <div>
            <b>Бровки из чертежа</b>
            <small>
              {scan.source_name || "чертёж"} · {scan.polylines.length} линий
              {scan.converted_from === "dwg" ? " · DWG сконвертирован в DXF" : ""}
              {scan.truncated ? " · показаны самые длинные" : ""}
            </small>
          </div>
          <button type="button" className="drawing-dialog-close" onClick={onCancel} aria-label="Закрыть">×</button>
        </header>

        <div className="drawing-dialog-body">
          <svg className="drawing-preview" viewBox={`0 0 ${PREVIEW_W} ${PREVIEW_H}`} role="img" aria-label="Предпросмотр чертежа">
            {scan.polylines.map((item) => {
              const role = roleOf(item.id);
              const hovered = hoverId === item.id;
              return (
                <path
                  key={item.id}
                  className={`drawing-preview-line${role ? ` role-${role}` : ""}${hovered ? " hovered" : ""}`}
                  d={path(item.points, item.closed)}
                  onMouseEnter={() => setHoverId(item.id)}
                  onMouseLeave={() => setHoverId("")}
                  onClick={() => assign(crestId && !toeId ? "toe" : "crest", item.id)}
                />
              );
            })}
          </svg>

          <div className="drawing-list-wrap">
            <input
              type="search"
              className="drawing-list-search"
              placeholder="Слой или тип линии…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              aria-label="Поиск линии"
            />
            <ul className="drawing-list">
              {visible.length === 0 && <li className="drawing-list-empty">Ничего не найдено</li>}
              {visible.map((item) => {
                const role = roleOf(item.id);
                return (
                  <li
                    key={item.id}
                    className={`${role ? `role-${role}` : ""}${hoverId === item.id ? " hovered" : ""}`}
                    onMouseEnter={() => setHoverId(item.id)}
                    onMouseLeave={() => setHoverId("")}
                  >
                    <div className="drawing-list-info">
                      <b>{item.layer || "без слоя"}</b>
                      <small>
                        {item.entity} · {item.points.length} т. · {ruNumber(item.length_m, 1)} м
                        {item.closed ? " · замкнута" : ""}
                        {item.area_m2 > 0 ? ` · ${ruNumber(item.area_m2, 0)} м²` : ""}
                        {" · Z "}{ruNumber(item.z_min, 1)}…{ruNumber(item.z_max, 1)}
                      </small>
                    </div>
                    <div className="drawing-list-actions">
                      <button
                        type="button"
                        className={role === "crest" ? "active" : ""}
                        onClick={() => assign("crest", item.id)}
                        title="Назначить верхней бровкой"
                      >
                        верх
                      </button>
                      <button
                        type="button"
                        className={role === "toe" ? "active" : ""}
                        onClick={() => assign("toe", item.id)}
                        title="Назначить нижней бровкой"
                      >
                        низ
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        </div>

        <footer>
          <div className="drawing-dialog-status">
            {error && <span className="drawing-dialog-error">{error}</span>}
            {!error && crest && toe && (
              <span>
                Верх Z {ruNumber((crest.z_min + crest.z_max) / 2, 1)} м · низ Z {ruNumber((toe.z_min + toe.z_max) / 2, 1)} м
                {crest.z_max <= toe.z_min && " · верхняя бровка ниже нижней, проверьте выбор"}
              </span>
            )}
            {!error && (!crest || !toe) && <span>Выберите верхнюю и нижнюю бровки.</span>}
          </div>
          <div className="drawing-dialog-actions">
            <button type="button" className="secondary-button" onClick={onCancel}>Отмена</button>
            <button
              type="button"
              className="primary-button"
              disabled={busy || !crest || !toe || sameLine}
              onClick={() => crest && toe && onApply({ crest, toe })}
            >
              {busy ? "Строю блок…" : "Построить блок"}
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}
