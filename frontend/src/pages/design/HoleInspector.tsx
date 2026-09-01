import { useEffect } from "react";
import { DeckShape } from "../../components/holeDrawing/DeckShape";
import { DepthScale } from "../../components/holeDrawing/DepthScale";
import { HoleBarrel } from "../../components/holeDrawing/HoleBarrel";
import { HoleDrawingDefs } from "../../components/holeDrawing/defs";
import { Primer } from "../../components/holeDrawing/Primer";
import { barrelWidthPx, makeAxis } from "../../components/holeDrawing/geometry";
import { ruNumber } from "../../lib/format";
import { angleAzimuth, holeFromCollar, holeLength } from "../../lib/geometry2d";
import type { Hole, HoleKind, HoleLoad } from "../../types/design";
import { HOLE_KIND_LABELS } from "../../types/design";

function round3(value: number): number {
  return Math.round(value * 1000) / 1000;
}

function geologySummary(hole: Hole): string {
  const designed = hole.intervals ?? [];
  if (!designed.length) return "—";
  return designed.map((iv) => `${iv.from_m.toFixed(0)}–${iv.to_m.toFixed(0)} ${iv.domain_name || iv.domain_id}`).join("; ");
}

export function HoleInspector({
  hole,
  load,
  locked = false,
  onClose,
  onUpdateHole,
  onSetEnabled,
  onDelete,
}: {
  hole: Hole;
  load?: HoleLoad;
  locked?: boolean;
  onClose: () => void;
  onUpdateHole: (id: string, patch: Partial<Hole>) => void;
  onSetEnabled: (ids: string[], enabled: boolean) => void;
  onDelete: (id: string) => void;
}) {
  const length = holeLength(hole.collar, hole.toe);
  const { angleDeg, azimuthDeg } = angleAzimuth(hole.collar, hole.toe);

  function patchAxis(next: { depth?: number; angle?: number; azimuth?: number }) {
    const current = angleAzimuth(hole.collar, hole.toe);
    const depth = next.depth ?? holeLength(hole.collar, hole.toe);
    const angle = next.angle ?? current.angleDeg;
    const azimuth = next.azimuth ?? current.azimuthDeg;
    onUpdateHole(hole.id, { toe: holeFromCollar(hole.collar, depth, angle, azimuth) });
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="hole-inspector-backdrop" onClick={onClose} role="presentation">
      <div
        className="hole-inspector"
        role="dialog"
        aria-labelledby="hole-inspector-title"
        onClick={(e) => e.stopPropagation()}
      >
        <header>
          <div>
            <h2 id="hole-inspector-title">Скважина {hole.id}</h2>
            <small>{HOLE_KIND_LABELS[hole.kind]} · {hole.source === "manual" ? "ручная" : "сетка"}</small>
          </div>
          <button type="button" className="stage-inspector-close" onClick={onClose} aria-label="Закрыть">×</button>
        </header>
        <div className="hole-inspector-grid">
          <fieldset className="workstation-lock hole-inspector-fields" disabled={locked}>
            <label>
              В расчёте
              <input
                type="checkbox"
                className="hole-enabled-toggle"
                checked={hole.enabled}
                onChange={(e) => onSetEnabled([hole.id], e.target.checked)}
              />
            </label>
            <label>
              Тип
              <select value={hole.kind} onChange={(e) => onUpdateHole(hole.id, { kind: e.target.value as HoleKind })}>
                {Object.entries(HOLE_KIND_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <div className="field-pair">
              <label>X устья, м<input value={ruNumber(hole.collar.x, 2)} readOnly /></label>
              <label>Y устья, м<input value={ruNumber(hole.collar.y, 2)} readOnly /></label>
            </div>
            <label>Z устья, м<input value={ruNumber(hole.collar.z, 2)} readOnly /></label>
            <div className="field-pair">
              <label>Забой X<input type="number" step="0.1" value={round3(hole.toe.x)} onChange={(e) => onUpdateHole(hole.id, { toe: { ...hole.toe, x: Number(e.target.value) } })} /></label>
              <label>Забой Y<input type="number" step="0.1" value={round3(hole.toe.y)} onChange={(e) => onUpdateHole(hole.id, { toe: { ...hole.toe, y: Number(e.target.value) } })} /></label>
            </div>
            <label>Забой Z<input type="number" step="0.1" value={round3(hole.toe.z)} onChange={(e) => onUpdateHole(hole.id, { toe: { ...hole.toe, z: Number(e.target.value) } })} /></label>
            <div className="field-pair">
              <label>Глубина, м<input type="number" step="0.1" value={round3(length)} onChange={(e) => patchAxis({ depth: Number(e.target.value) })} /></label>
              <label>Угол, °<input type="number" step="0.5" value={round3(angleDeg)} onChange={(e) => patchAxis({ angle: Number(e.target.value) })} /></label>
            </div>
            <div className="field-pair">
              <label>Азимут, °<input type="number" step="1" value={round3(azimuthDeg)} onChange={(e) => patchAxis({ azimuth: Number(e.target.value) })} /></label>
              <label>Ø, мм<input type="number" value={hole.diameter_mm} onChange={(e) => onUpdateHole(hole.id, { diameter_mm: Number(e.target.value) })} /></label>
            </div>
            <label>Перебур, м<input type="number" step="0.1" value={hole.subdrill_m} onChange={(e) => onUpdateHole(hole.id, { subdrill_m: Number(e.target.value) })} /></label>
            <small>Геология: {geologySummary(hole)}</small>
            <button type="button" className="danger-button" onClick={() => onDelete(hole.id)}>Удалить скважину</button>
          </fieldset>
          <ChargeSketch hole={hole} load={load} />
        </div>
      </div>
    </div>
  );
}

function ChargeSketch({ hole, load }: { hole: Hole; load?: HoleLoad }) {
  const depthM = holeLength(hole.collar, hole.toe);
  if (depthM <= 0) {
    return <div className="hole-charge-empty">Нет геометрии заряда</div>;
  }
  const width = 220;
  const height = 360;
  const pad = { left: 40, right: 58, top: 28, bottom: 24 };
  const yTop = pad.top;
  const yBottom = height - pad.bottom;
  const xAxis = pad.left + (width - pad.left - pad.right) / 2;
  const barrelW = barrelWidthPx(hole.diameter_mm, { min: 18, max: 36, base: 152 });
  const axis = makeAxis({ x: xAxis, y: yTop }, { x: xAxis, y: yBottom }, depthM, barrelW);
  const prefix = `hi-${hole.id}`;
  const subdrillFromM = Math.max(0, depthM - hole.subdrill_m);
  const decks = load?.decks ?? [];
  const primers = load?.primer_items ?? [];

  return (
    <div className="hole-charge-sketch">
      <b>Конструкция заряда</b>
      {load ? (
        <small>{ruNumber(load.total_charge_kg, 1)} кг · q {ruNumber(load.specific_q_kg_m3, 3)} кг/м³</small>
      ) : (
        <small>Заряд ещё не рассчитан</small>
      )}
      <svg viewBox={`0 0 ${width} ${height}`} className="hole-charge-svg" aria-label="Схема заряда">
        <HoleDrawingDefs prefix={prefix} />
        <HoleBarrel axis={axis} prefix={prefix} subdrillFromM={subdrillFromM} />
        {decks.map((deck, index) => (
          <DeckShape
            key={`${deck.kind}-${index}`}
            axis={axis}
            prefix={prefix}
            deck={deck}
            title={deck.explosive_key || deck.product || deck.kind}
          />
        ))}
        {primers.map((item, index) => (
          <Primer
            key={`${item.position_m}-${index}`}
            axis={axis}
            depthM={item.position_m}
            label={`Д${index + 1}`}
            nsiExitPx={10}
            nsiOffsetPx={index * 4}
          />
        ))}
        <DepthScale
          x={pad.left - 8}
          yTop={yTop}
          yBottom={yBottom}
          fromValue={0}
          toValue={depthM}
          toY={(value) => axis.at(value).y}
        />
      </svg>
    </div>
  );
}
