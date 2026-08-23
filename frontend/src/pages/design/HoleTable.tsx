import { ruNumber } from "../../lib/format";
import type { Hole, HoleKind } from "../../types/design";

const KIND_LABELS: Record<HoleKind, string> = {
  production: "Рабочая",
  contour: "Контурная",
  presplit: "Предщелевая",
  trim: "Оконтуривающая",
};

export function HoleTable({
  holes,
  selected,
  onSelectedChange,
  onUpdateHole,
  onDeleteSelected,
  onSetEnabled,
}: {
  holes: Hole[];
  selected: Set<string>;
  onSelectedChange: (ids: Set<string>) => void;
  onUpdateHole: (id: string, patch: Partial<Hole>) => void;
  onDeleteSelected: () => void;
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

  const selectedHoles = holes.filter((h) => selected.has(h.id));
  const allSelectedEnabled = selectedHoles.every((h) => h.enabled);
  const disabledCount = selectedHoles.filter((h) => !h.enabled).length;

  return (
    <section className="panel hole-table-panel">
      <header>
        <b>Скважины</b>
        <span>{holes.length ? `${holes.length} шт.` : "Пусто"}</span>
      </header>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th></th><th title="Скважина участвует в расчёте">Вкл.</th><th>ID</th><th>Тип</th><th>X, м</th><th>Y, м</th><th>Глубина, м</th><th>Ø, мм</th><th>Перебур, м</th>
            </tr>
          </thead>
          <tbody>
            {holes.map((h) => {
              const length = Math.sqrt(
                (h.toe.x - h.collar.x) ** 2 + (h.toe.y - h.collar.y) ** 2 + (h.toe.z - h.collar.z) ** 2,
              );
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
                      {Object.entries(KIND_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                    </select>
                  </td>
                  <td>{ruNumber(h.collar.x, 2)}</td>
                  <td>{ruNumber(h.collar.y, 2)}</td>
                  <td>{ruNumber(length, 2)}</td>
                  <td>
                    <input type="number" value={h.diameter_mm} onClick={(e) => e.stopPropagation()} onChange={(e) => onUpdateHole(h.id, { diameter_mm: Number(e.target.value) })} />
                  </td>
                  <td>
                    <input type="number" step="0.1" value={h.subdrill_m} onClick={(e) => e.stopPropagation()} onChange={(e) => onUpdateHole(h.id, { subdrill_m: Number(e.target.value) })} />
                  </td>
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
