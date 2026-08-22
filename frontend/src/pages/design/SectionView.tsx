import { useMemo } from "react";
import { holeLength, localBasis } from "../../lib/geometry2d";
import { ruNumber } from "../../lib/format";
import type { BlockContour, Hole, HoleLoad } from "../../types/design";

const DECK_CLASS: Record<string, string> = {
  charge: "deck-charge",
  stemming: "deck-stemming",
  air: "deck-air",
};

export function SectionView({
  contour,
  holes,
  loads,
  rowAzimuthDeg,
  selectedRow,
  onSelectedRowChange,
}: {
  contour: BlockContour;
  holes: Hole[];
  loads: HoleLoad[];
  rowAzimuthDeg: number;
  selectedRow: number | null;
  onSelectedRowChange: (row: number) => void;
}) {
  const loadById = useMemo(() => {
    const map = new Map<string, HoleLoad>();
    for (const load of loads) map.set(load.hole_id, load);
    return map;
  }, [loads]);

  const rows = useMemo(() => {
    const set = new Set<number>();
    for (const h of holes) if (h.enabled) set.add(h.row);
    return Array.from(set).sort((a, b) => a - b);
  }, [holes]);

  const { rowDir } = useMemo(() => localBasis(rowAzimuthDeg), [rowAzimuthDeg]);
  const row = selectedRow ?? rows[0] ?? null;
  const rowHoles = useMemo(() => {
    if (row === null) return [];
    return holes
      .filter((h) => h.enabled && h.row === row)
      .map((h) => ({ hole: h, u: h.collar.x * rowDir.x + h.collar.y * rowDir.y }))
      .sort((a, b) => a.u - b.u);
  }, [holes, row, rowDir]);

  if (!rows.length) {
    return (
      <section className="panel">
        <header><b>Разрез по ряду</b></header>
        <div className="panel-body"><small>Постройте сетку скважин, чтобы увидеть разрез.</small></div>
      </section>
    );
  }

  const width = 760;
  const height = 320;
  const pad = { left: 50, right: 20, top: 20, bottom: 30 };

  const uValues = rowHoles.map((r) => r.u);
  const zValues = rowHoles.flatMap((r) => [r.hole.collar.z, r.hole.toe.z]);
  zValues.push(contour.bench.crest_z_m, contour.bench.toe_z_m);
  const uMin = Math.min(...uValues) - 1;
  const uMax = Math.max(...uValues) + 1;
  const zMin = Math.min(...zValues) - 1;
  const zMax = Math.max(...zValues) + 1;

  const sx = (u: number) => pad.left + ((u - uMin) / Math.max(1e-6, uMax - uMin)) * (width - pad.left - pad.right);
  const sy = (z: number) => pad.top + ((zMax - z) / Math.max(1e-6, zMax - zMin)) * (height - pad.top - pad.bottom);

  function pointAt(hole: Hole, t: number): { x: number; y: number } {
    const u = hole.collar.x * rowDir.x + hole.collar.y * rowDir.y;
    const uToe = hole.toe.x * rowDir.x + hole.toe.y * rowDir.y;
    return { x: sx(u + t * (uToe - u)), y: sy(hole.collar.z + t * (hole.toe.z - hole.collar.z)) };
  }

  return (
    <section className="panel section-view-panel">
      <header>
        <b>Разрез по ряду</b>
        <select value={row ?? ""} onChange={(e) => onSelectedRowChange(Number(e.target.value))}>
          {rows.map((r) => <option key={r} value={r}>{r < 0 ? `Контур ${-r}` : `Ряд ${r + 1}`}</option>)}
        </select>
      </header>
      <div className="panel-body">
        <svg className="section-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Разрез по ряду скважин">
          <line x1={pad.left} y1={sy(contour.bench.crest_z_m)} x2={width - pad.right} y2={sy(contour.bench.crest_z_m)} className="section-bench-line" />
          <line x1={pad.left} y1={sy(contour.bench.toe_z_m)} x2={width - pad.right} y2={sy(contour.bench.toe_z_m)} className="section-bench-line" />
          <text x={pad.left} y={sy(contour.bench.crest_z_m) - 4} className="section-label">бровка</text>
          <text x={pad.left} y={sy(contour.bench.toe_z_m) - 4} className="section-label">подошва</text>

          {rowHoles.map(({ hole }) => {
            const load = loadById.get(hole.id);
            const collarPx = { x: sx(hole.collar.x * rowDir.x + hole.collar.y * rowDir.y), y: sy(hole.collar.z) };
            const toePx = { x: sx(hole.toe.x * rowDir.x + hole.toe.y * rowDir.y), y: sy(hole.toe.z) };
            const length = holeLength(hole.collar, hole.toe) || 1;
            return (
              <g key={hole.id}>
                <line x1={collarPx.x} y1={collarPx.y} x2={toePx.x} y2={toePx.y} className="section-hole-outline" />
                {load?.decks.map((deck, i) => {
                  const from = pointAt(hole, length > 0 ? deck.from_m / length : 0);
                  const to = pointAt(hole, length > 0 ? deck.to_m / length : 0);
                  return (
                    <line
                      key={i}
                      x1={from.x}
                      y1={from.y}
                      x2={to.x}
                      y2={to.y}
                      className={`section-deck ${DECK_CLASS[deck.kind] ?? ""}`}
                    />
                  );
                })}
                <circle cx={collarPx.x} cy={collarPx.y} r={4} className="section-collar" />
                <text x={collarPx.x} y={collarPx.y - 8} className="section-label" textAnchor="middle">{hole.id}</text>
                {load && load.total_charge_kg > 0 && (
                  <text x={toePx.x} y={toePx.y + 14} className="section-label" textAnchor="middle">
                    {ruNumber(load.total_charge_kg, 0)} кг
                  </text>
                )}
              </g>
            );
          })}
        </svg>
        <div className="section-legend">
          <span><i className="deck-charge" /> заряд</span>
          <span><i className="deck-stemming" /> забойка</span>
          <span><i className="deck-air" /> промежуток</span>
        </div>
      </div>
    </section>
  );
}
