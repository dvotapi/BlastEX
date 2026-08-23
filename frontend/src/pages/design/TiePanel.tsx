import {
  ELECTRONIC_MODE_OPTIONS,
  networkTies,
  type InitiationNetwork,
  type SchemeType,
  type SurfaceConnector,
  type SystemType,
  type TieParams,
} from "../../types/design";
import { RoleBadge } from "./RoleBadge";

const SCHEME_OPTIONS: { value: SchemeType; label: string; hint: string }[] = [
  { value: "row", label: "Порядная", hint: "фронт по рядам" },
  { value: "echelon", label: "Клиновая", hint: "диагональная лестница" },
  { value: "diagonal_v", label: "Диагональная V", hint: "от центра ряда" },
  { value: "trapezoid", label: "Трапецеидальная", hint: "от флангов к центру" },
];

const SYSTEM_OPTIONS: { value: SystemType; label: string }[] = [
  { value: "nonel", label: "Неэлектрическая (СИНВ)" },
  { value: "electronic", label: "Электронные детонаторы" },
  { value: "detcord", label: "ДШ + пиротехн. реле" },
];

export function TiePanel({
  scheme,
  params,
  network,
  selectedCount,
  pendingFromId,
  onSchemeChange,
  onParamsChange,
  onGenerate,
  onUpdateTie,
  onRemoveTie,
  onToggleStarters,
  busy,
}: {
  scheme: SchemeType;
  params: TieParams;
  network: InitiationNetwork;
  selectedCount: number;
  pendingFromId: string | null;
  onSchemeChange: (scheme: SchemeType) => void;
  onParamsChange: (patch: Partial<TieParams>) => void;
  onGenerate: () => void;
  onUpdateTie: (connector: SurfaceConnector, delayMs: number) => void;
  onRemoveTie: (connectorId: string) => void;
  onToggleStarters: () => void;
  busy: boolean;
}) {
  const ties = networkTies(network);
  const electronic = params.system === "electronic";
  const mode = params.timing_mode;

  return (
    <section className="panel">
      <header><b>Коммутация</b><RoleBadge role="designed" /></header>
      <div className="panel-body">
        <label>Система инициирования
          <select value={params.system} onChange={(e) => onParamsChange({ system: e.target.value as SystemType })}>
            {SYSTEM_OPTIONS.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
          </select>
        </label>

        {electronic && (
          <>
            <small>Электронный тайминг</small>
            <div className="pattern-type-grid">
              {ELECTRONIC_MODE_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  className={`pattern-type-option${mode === opt.value ? " active" : ""}`}
                  onClick={() => onParamsChange({ timing_mode: opt.value })}
                >
                  <b>{opt.label}</b>
                  <small>{opt.hint}</small>
                </button>
              ))}
            </div>
          </>
        )}

        <small>Шаблон связей</small>
        <div className="pattern-type-grid">
          {SCHEME_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              className={`pattern-type-option${scheme === opt.value ? " active" : ""}`}
              onClick={() => onSchemeChange(opt.value)}
            >
              <b>{opt.label}</b>
              <small>{opt.hint}</small>
            </button>
          ))}
        </div>

        <div className="field-pair">
          <label>Интервал замедления, мс
            <input type="number" min="1" step="1" value={params.interval_ms} onChange={(e) => onParamsChange({ interval_ms: Number(e.target.value) })} />
          </label>
          <label>Внутрискважинное замедление, мс
            <input type="number" min="0" step="10" value={params.downhole_delay_ms} onChange={(e) => onParamsChange({ downhole_delay_ms: Number(e.target.value) })} />
          </label>
        </div>

        {electronic && mode === "direction" && (
          <label>Азимут направления, °
            <input type="number" step="5" value={params.direction_azimuth_deg} onChange={(e) => onParamsChange({ direction_azimuth_deg: Number(e.target.value) })} />
          </label>
        )}
        {electronic && mode === "gradient" && (
          <div className="field-pair">
            <label>От, мс
              <input type="number" step="1" value={params.gradient_from_ms} onChange={(e) => onParamsChange({ gradient_from_ms: Number(e.target.value) })} />
            </label>
            <label>До, мс
              <input type="number" step="1" value={params.gradient_to_ms} onChange={(e) => onParamsChange({ gradient_to_ms: Number(e.target.value) })} />
            </label>
          </div>
        )}
        {electronic && mode === "expression" && (
          <label>Выражение времени
            <input
              type="text"
              value={params.timing_expression}
              placeholder="base + interval * row + abs(col - 3)"
              onChange={(e) => onParamsChange({ timing_expression: e.target.value })}
            />
          </label>
        )}
        {electronic && (
          <label>База, мс
            <input type="number" min="0" step="1" value={params.base_ms} onChange={(e) => onParamsChange({ base_ms: Number(e.target.value) })} />
          </label>
        )}

        <label className="checkbox-row">
          <input type="checkbox" checked={params.include_contour} onChange={(e) => onParamsChange({ include_contour: e.target.checked })} />
          Включить контурные скважины в схему
        </label>

        <button className="calculate-button" onClick={onGenerate} disabled={busy}>
          {busy ? "Строим схему…" : electronic && mode ? "Назначить электронный тайминг" : "Построить схему"}
        </button>
        <small>
          {electronic
            ? "Время задаётся программой канала. Выражение: row, col, x, y, interval, base, abs/min/max. Без eval."
            : "Для НСИ интервал округляется до номинала (17/25/42/67/109 мс), для ДШ — до номинала реле."}
        </small>

        <div className="tie-edit-block">
          <b>Ручная правка связей</b>
          <small>
            {pendingFromId
              ? `От ${pendingFromId}: кликните вторую скважину на плане.`
              : "Клик по двум скважинам добавляет связь. Выделение + кнопка ниже — стартовые."}
          </small>
          <button className="secondary-button" type="button" onClick={onToggleStarters} disabled={!selectedCount}>
            Стартовые из выделенных ({selectedCount})
          </button>
          {ties.length === 0 ? (
            <small>Связей пока нет.</small>
          ) : (
            <div className="tie-list">
              {ties.map((tie) => (
                <div key={tie.id} className="tie-row">
                  <span>{tie.from_hole} → {tie.to_hole}</span>
                  <input
                    type="number"
                    min="0"
                    step="1"
                    value={tie.delay_ms}
                    onChange={(e) => onUpdateTie(tie, Number(e.target.value))}
                  />
                  <button type="button" className="ghost-button" onClick={() => onRemoveTie(tie.id)}>×</button>
                </div>
              ))}
            </div>
          )}
          <small>
            Стартовых: {network.starter_items?.length || network.starters.length}
            {network.electronic_channels?.length ? ` · каналов: ${network.electronic_channels.length}` : ""}
            {network.detonating_cords?.length ? ` · ДШ: ${network.detonating_cords.length}` : ""}
          </small>
        </div>
      </div>
    </section>
  );
}
