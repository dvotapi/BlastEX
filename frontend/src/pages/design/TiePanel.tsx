import {
  DETCORD_RELAY_MS_OPTIONS,
  ELECTRONIC_MODE_OPTIONS,
  networkTies,
  SURFACE_NSI_MS_OPTIONS,
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
  { value: "trunk_chains", label: "Магистраль + цепочки", hint: "вруб у фланга, 25 / 42 мс" },
];

const SYSTEM_OPTIONS: { value: SystemType; label: string }[] = [
  { value: "nonel", label: "Неэлектрическая (СИНВ)" },
  { value: "electronic", label: "Электронные детонаторы" },
  { value: "detcord", label: "ДШ + пиротехн. реле" },
];

// Ступени «Магистраль + цепочки» при смене системы — к ближайшему номиналу новой
// системы (как design/timing.py::_snap: при равенстве — меньший); у электронной
// номиналов нет — ступень остаётся.
function nearestStep(value: number, options: readonly number[]): number {
  return options.reduce((best, option) => (Math.abs(option - value) < Math.abs(best - value) ? option : best));
}

function stepsForSystem(system: SystemType, params: TieParams): Pick<TieParams, "trunk_ms" | "chain_ms"> {
  if (system === "electronic") return { trunk_ms: params.trunk_ms, chain_ms: params.chain_ms };
  const options = system === "detcord" ? DETCORD_RELAY_MS_OPTIONS : SURFACE_NSI_MS_OPTIONS;
  return { trunk_ms: nearestStep(params.trunk_ms, options), chain_ms: nearestStep(params.chain_ms, options) };
}

export function TiePanel({
  scheme,
  params,
  network,
  selectedCount,
  pendingFromId,
  warnings,
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
  warnings: string[];
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
  const trunkChains = scheme === "trunk_chains";
  // Режимы электронного тайминга схеме «Магистраль + цепочки» не применяются:
  // времена — по связям.
  const electronicModes = electronic && !trunkChains;
  // Внутрискважинное замедление СИНВ при этой схеме подбирает сервер; поле
  // показывает выбранное, только если текущая сеть построена этой схемой и
  // этой системой (у сети ДШ/электронной там умолчание системы, а не подбор).
  const downholeAuto = trunkChains && params.system === "nonel";
  const pickedDownhole =
    network.timing_params?.scheme === "trunk_chains" && network.system === params.system
      ? network.timing_params.downhole_delay_ms
      : undefined;
  const downholeValue = downholeAuto
    ? typeof pickedDownhole === "number" ? pickedDownhole : ""
    : params.downhole_delay_ms;
  const stepOptions = params.system === "detcord" ? DETCORD_RELAY_MS_OPTIONS : SURFACE_NSI_MS_OPTIONS;

  return (
    <section className="panel">
      <header><b>Коммутация</b><RoleBadge role="designed" /></header>
      <div className="panel-body">
        <label>Система инициирования
          <select
            value={params.system}
            onChange={(e) => {
              const system = e.target.value as SystemType;
              onParamsChange({ system, ...stepsForSystem(system, params) });
            }}
          >
            {SYSTEM_OPTIONS.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
          </select>
        </label>

        {electronicModes && (
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
              onClick={() => {
                onSchemeChange(opt.value);
                // Режим электронного тайминга, выбранный при другой схеме, этой
                // схеме не применяется и скрыт — не отправляем его серверу.
                if (opt.value === "trunk_chains" && params.timing_mode) onParamsChange({ timing_mode: "" });
              }}
            >
              <b>{opt.label}</b>
              <small>{opt.hint}</small>
            </button>
          ))}
        </div>

        {trunkChains ? (
          <>
            {electronic ? (
              // Электронный детонатор программируется с точностью 1 мс: номиналов нет.
              <div className="field-pair">
                <label>Магистраль, мс
                  <input type="number" min="1" step="1" value={params.trunk_ms} onChange={(e) => onParamsChange({ trunk_ms: Number(e.target.value) })} />
                </label>
                <label>Цепочки, мс
                  <input type="number" min="1" step="1" value={params.chain_ms} onChange={(e) => onParamsChange({ chain_ms: Number(e.target.value) })} />
                </label>
              </div>
            ) : (
              <div className="field-pair">
                <label>Магистраль, мс
                  <select value={params.trunk_ms} onChange={(e) => onParamsChange({ trunk_ms: Number(e.target.value) })}>
                    {stepOptions.map((ms) => <option key={ms} value={ms}>{ms}</option>)}
                  </select>
                </label>
                <label>Цепочки, мс
                  <select value={params.chain_ms} onChange={(e) => onParamsChange({ chain_ms: Number(e.target.value) })}>
                    {stepOptions.map((ms) => <option key={ms} value={ms}>{ms}</option>)}
                  </select>
                </label>
              </div>
            )}
            <label>Вруб у фланга
              <select value={params.cut_flank} onChange={(e) => onParamsChange({ cut_flank: e.target.value as "left" | "right" })}>
                <option value="left">левого</option>
                <option value="right">правого</option>
              </select>
            </label>
            <small>Фланг — если смотреть с откоса на блок.</small>
            <label>Внутрискважинное замедление, мс
              <input
                type="number"
                min="0"
                step="10"
                value={downholeValue}
                placeholder={downholeAuto ? "подбирается" : undefined}
                disabled={downholeAuto}
                onChange={(e) => onParamsChange({ downhole_delay_ms: Number(e.target.value) })}
              />
            </label>
            {downholeAuto && <small>Подбирается: наименьшее из 500 / 700 / 1000 мс, при котором сеть успевает до первого взрыва.</small>}
          </>
        ) : (
          <div className="field-pair">
            <label>Интервал замедления, мс
              <input type="number" min="1" step="1" value={params.interval_ms} onChange={(e) => onParamsChange({ interval_ms: Number(e.target.value) })} />
            </label>
            <label>Внутрискважинное замедление, мс
              <input type="number" min="0" step="10" value={params.downhole_delay_ms} onChange={(e) => onParamsChange({ downhole_delay_ms: Number(e.target.value) })} />
            </label>
          </div>
        )}

        {electronicModes && mode === "direction" && (
          <label>Азимут направления, °
            <input type="number" step="5" value={params.direction_azimuth_deg} onChange={(e) => onParamsChange({ direction_azimuth_deg: Number(e.target.value) })} />
          </label>
        )}
        {electronicModes && mode === "gradient" && (
          <div className="field-pair">
            <label>От, мс
              <input type="number" step="1" value={params.gradient_from_ms} onChange={(e) => onParamsChange({ gradient_from_ms: Number(e.target.value) })} />
            </label>
            <label>До, мс
              <input type="number" step="1" value={params.gradient_to_ms} onChange={(e) => onParamsChange({ gradient_to_ms: Number(e.target.value) })} />
            </label>
          </div>
        )}
        {electronicModes && mode === "expression" && (
          <label>Выражение времени
            <input
              type="text"
              value={params.timing_expression}
              placeholder="base + interval * row + abs(col - 3)"
              onChange={(e) => onParamsChange({ timing_expression: e.target.value })}
            />
          </label>
        )}
        {electronicModes && (
          <label>База, мс
            <input type="number" min="0" step="1" value={params.base_ms} onChange={(e) => onParamsChange({ base_ms: Number(e.target.value) })} />
          </label>
        )}

        <label className="checkbox-row">
          <input type="checkbox" checked={params.include_contour} onChange={(e) => onParamsChange({ include_contour: e.target.checked })} />
          Включить контурные скважины в схему
        </label>

        <button className="calculate-button" onClick={onGenerate} disabled={busy}>
          {busy ? "Строим схему…" : electronicModes && mode ? "Назначить электронный тайминг" : "Построить схему"}
        </button>
        {warnings.map((text, index) => <small key={index} className="frag-warnings">{text}</small>)}
        <small>
          {trunkChains
            ? "Ступени округляются до номинала: НСИ — 17/25/42/67/109 мс, ДШ — 10/20/25/35/42 мс; у электронных — любые, от 1 мс."
            : electronic
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
