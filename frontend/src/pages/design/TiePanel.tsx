import type { SchemeType, SystemType, TieParams } from "../../types/design";

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
  onSchemeChange,
  onParamsChange,
  onGenerate,
  busy,
}: {
  scheme: SchemeType;
  params: TieParams;
  onSchemeChange: (scheme: SchemeType) => void;
  onParamsChange: (patch: Partial<TieParams>) => void;
  onGenerate: () => void;
  busy: boolean;
}) {
  return (
    <section className="panel">
      <header><b>Коммутация</b><span>04</span></header>
      <div className="panel-body">
        <label>Система инициирования
          <select value={params.system} onChange={(e) => onParamsChange({ system: e.target.value as SystemType })}>
            {SYSTEM_OPTIONS.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
          </select>
        </label>

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

        <label className="checkbox-row">
          <input type="checkbox" checked={params.include_contour} onChange={(e) => onParamsChange({ include_contour: e.target.checked })} />
          Включить контурные скважины в схему
        </label>

        <button className="calculate-button" onClick={onGenerate} disabled={busy}>
          {busy ? "Строим схему…" : "Построить схему"}
        </button>
        <small>
          Для НСИ интервал округляется до ближайшего номинала (17/25/42/67/109 мс), для ДШ — до
          номинала реле. Внутрискважинное замедление одинаково для всех скважин.
        </small>
      </div>
    </section>
  );
}
