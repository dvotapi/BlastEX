import { angleAzimuth, holeFromCollar, holeLength } from "../../lib/geometry2d";
import { ruNumber } from "../../lib/format";
import type { Hole, HoleKind } from "../../types/design";
import { HOLE_KIND_LABELS } from "../../types/design";

export function HoleTable({
  holes,
  selected,
  onSelectedChange,
  onUpdateHole,
  onDeleteSelected,
  insertKind,
  onInsertKindChange,
  onSetEnabled,
}: {
  holes: Hole[];
  selected: Set<string>;
  onSelectedChange: (ids: Set<string>) => void;
  onUpdateHole: (id: string, patch: Partial<Hole>) => void;
  onDeleteSelected: () => void;
  insertKind: HoleKind;
  onInsertKindChange: (kind: HoleKind) => void;
  onSetEnabled: (ids: string[], enabled: boolean) => void;
}) {
  function toggleRow(id: string, additive: boolean) {
    if (!additive) {
      onSelectedChange(new Set(selected.has(id) && selected.size === 1 ? [] : [id]));
      return;
    }
    const next = new Set(selected);
    if (next.has(id)) next.delete(id); else next.add(id);
    onSelectedChange(next);
  }

  function patchAxis(hole: Hole, next: { depth?: number; angle?: number; azimuth?: number }) {
    const current = angleAzimuth(hole.collar, hole.toe);
    const depth = next.depth ?? holeLength(hole.collar, hole.toe);
    const angle = next.angle ?? current.angleDeg;
    const azimuth = next.azimuth ?? current.azimuthDeg;
    onUpdateHole(hole.id, { toe: holeFromCollar(hole.collar, depth, angle, azimuth) });
  }

  const selectedHoles = holes.filter((h) => selected.has(h.id));
  const allSelectedEnabled = selectedHoles.every((h) => h.enabled);
  const disabledCount = selectedHoles.filter((h) => !h.enabled).length;

  return (
    <section className="panel hole-table-panel">
      <header>
        <b>Скважины</b>
        <span>{holes.length ? `${holes.length} шт.` : "Пусто"}</span>
      </header>
      <div className="hole-insert-kind">
        <label>
          Тип новой скважины
          <select value={insertKind} onChange={(e) => onInsertKindChange(e.target.value as HoleKind)}>
            {Object.entries(HOLE_KIND_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <small>Двойной клик по плану добавляет ручную скважину этого типа.</small>
      </div>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th></th>
              <th title="Скважина участвует в расчёте">Вкл.</th>
              <th>ID</th>
              <th>Тип</th>
              <th>X, м</th>
              <th>Y, м</th>
              <th>Z устья</th>
              <th>Забой X</th>
              <th>Забой Y</th>
              <th>Забой Z</th>
              <th>Глубина</th>
              <th>Угол, °</th>
              <th>Азимут, °</th>
              <th>Ø, мм</th>
              <th>Перебур</th>
              <th>Источник</th>
              <th>Геология</th>
            </tr>
          </thead>
          <tbody>
            {holes.map((h) => {
              const length = holeLength(h.collar, h.toe);
              const { angleDeg, azimuthDeg } = angleAzimuth(h.collar, h.toe);
              return (
                <tr
                  key={h.id}
                  className={`${selected.has(h.id) ? "selected" : ""}${h.enabled ? "" : " disabled"}`.trim()}
                  onClick={(e) => toggleRow(h.id, e.shiftKey || e.metaKey || e.ctrlKey)}
                >
                  <td><span className="row-radio" /></td>
                  <td>
                    <input
                      type="checkbox"
                      className="hole-enabled-toggle"
                      checked={h.enabled}
                      title={h.enabled ? "Исключить скважину из расчёта" : "Вернуть скважину в расчёт"}
                      aria-label={`Скважина ${h.id} участвует в расчёте`}
                      onClick={(e) => e.stopPropagation()}
                      onChange={(e) => onSetEnabled([h.id], e.target.checked)}
                    />
                  </td>
                  <td><b>{h.id}</b></td>
                  <td>
                    <select value={h.kind} onClick={(e) => e.stopPropagation()} onChange={(e) => onUpdateHole(h.id, { kind: e.target.value as HoleKind })}>
                      {Object.entries(HOLE_KIND_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                    </select>
                  </td>
                  <td>{ruNumber(h.collar.x, 2)}</td>
                  <td>{ruNumber(h.collar.y, 2)}</td>
                  <td>{ruNumber(h.collar.z, 2)}</td>
                  <td>
                    <input type="number" step="0.1" value={round3(h.toe.x)} onClick={(e) => e.stopPropagation()} onChange={(e) => onUpdateHole(h.id, { toe: { ...h.toe, x: Number(e.target.value) } })} />
                  </td>
                  <td>
                    <input type="number" step="0.1" value={round3(h.toe.y)} onClick={(e) => e.stopPropagation()} onChange={(e) => onUpdateHole(h.id, { toe: { ...h.toe, y: Number(e.target.value) } })} />
                  </td>
                  <td>
                    <input type="number" step="0.1" value={round3(h.toe.z)} onClick={(e) => e.stopPropagation()} onChange={(e) => onUpdateHole(h.id, { toe: { ...h.toe, z: Number(e.target.value) } })} />
                  </td>
                  <td>
                    <input type="number" step="0.1" value={round3(length)} onClick={(e) => e.stopPropagation()} onChange={(e) => patchAxis(h, { depth: Number(e.target.value) })} />
                  </td>
                  <td>
                    <input type="number" step="0.5" value={round3(angleDeg)} onClick={(e) => e.stopPropagation()} onChange={(e) => patchAxis(h, { angle: Number(e.target.value) })} />
                  </td>
                  <td>
                    <input type="number" step="1" value={round3(azimuthDeg)} onClick={(e) => e.stopPropagation()} onChange={(e) => patchAxis(h, { azimuth: Number(e.target.value) })} />
                  </td>
                  <td>
                    <input type="number" value={h.diameter_mm} onClick={(e) => e.stopPropagation()} onChange={(e) => onUpdateHole(h.id, { diameter_mm: Number(e.target.value) })} />
                  </td>
                  <td>
                    <input type="number" step="0.1" value={h.subdrill_m} onClick={(e) => e.stopPropagation()} onChange={(e) => onUpdateHole(h.id, { subdrill_m: Number(e.target.value) })} />
                  </td>
                  <td>{h.source === "manual" ? "ручная" : "сетка"}</td>
                  <td>{geologySummary(h)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {selected.size > 0 && (
        <div className="hole-table-actions">
          <span>{selected.size} выбрано{disabledCount ? ` · ${disabledCount} вне расчёта` : ""}</span>
          <div className="hole-table-buttons">
            <button onClick={() => onSetEnabled(Array.from(selected), !allSelectedEnabled)}>
              {allSelectedEnabled ? "Исключить из расчёта" : "Вернуть в расчёт"}
            </button>
            <button className="danger-button" onClick={onDeleteSelected}>Удалить</button>
          </div>
        </div>
      )}
    </section>
  );
}

function geologySummary(hole: Hole): string {
  const designed = hole.intervals ?? [];
  if (!designed.length) return "—";
  return designed.map((iv) => `${iv.from_m.toFixed(0)}–${iv.to_m.toFixed(0)} ${iv.domain_name || iv.domain_id}`).join("; ");
}

function round3(value: number): number {
  return Math.round(value * 1000) / 1000;
}
