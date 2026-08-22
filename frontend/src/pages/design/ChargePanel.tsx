import type { Explosive } from "../../types";
import type { ChargeRules, DeckingType } from "../../types/design";

export function ChargePanel({
  rules,
  explosives,
  explosiveKey,
  onExplosiveKeyChange,
  onChange,
  onCalculate,
  busy,
}: {
  rules: ChargeRules;
  explosives: Explosive[];
  explosiveKey: string;
  onExplosiveKeyChange: (key: string) => void;
  onChange: (patch: Partial<ChargeRules>) => void;
  onCalculate: () => void;
  busy: boolean;
}) {
  function num(key: keyof ChargeRules) {
    return {
      value: rules[key] as number,
      onChange: (e: React.ChangeEvent<HTMLInputElement>) => onChange({ [key]: Number(e.target.value) } as Partial<ChargeRules>),
    };
  }

  const stemmingFixed = rules.stemming_m !== null;

  return (
    <section className="panel">
      <header><b>Заряжание</b><span>03</span></header>
      <div className="panel-body">
        <label>Взрывчатое вещество
          <select value={explosiveKey} onChange={(e) => onExplosiveKeyChange(e.target.value)}>
            {explosives.map((item) => <option key={item.key} value={item.key}>{item.name}</option>)}
          </select>
        </label>

        <label>Коэффициент разбуривания<input type="number" min="1" max="1.5" step="0.01" {...num("hole_oversize_coeff")} /></label>

        <div className="pattern-type-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
          <button
            type="button"
            className={`pattern-type-option${stemmingFixed ? " active" : ""}`}
            onClick={() => onChange({ stemming_m: rules.stemming_m ?? 3 })}
          >
            <b>Забойка, м</b><small>фиксированная длина</small>
          </button>
          <button
            type="button"
            className={`pattern-type-option${!stemmingFixed ? " active" : ""}`}
            onClick={() => onChange({ stemming_m: null })}
          >
            <b>Забойка, k×d</b><small>по диаметру скважины</small>
          </button>
        </div>
        {stemmingFixed ? (
          <label>Длина забойки, м
            <input type="number" min="0" step="0.1" value={rules.stemming_m ?? 0} onChange={(e) => onChange({ stemming_m: Number(e.target.value) })} />
          </label>
        ) : (
          <label>Забойка, диаметров скважины<input type="number" min="1" step="1" {...num("stemming_k")} /></label>
        )}

        <div className="pattern-type-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
          {(["continuous", "spaced"] as DeckingType[]).map((value) => (
            <button
              key={value}
              type="button"
              className={`pattern-type-option${rules.decking === value ? " active" : ""}`}
              onClick={() => onChange({ decking: value })}
            >
              <b>{value === "continuous" ? "Сплошной заряд" : "Рассредоточенный"}</b>
              <small>{value === "continuous" ? "одна колонна" : "деки + промежутки"}</small>
            </button>
          ))}
        </div>

        {rules.decking === "spaced" && (
          <div className="field-pair">
            <label>Число зарядов<input type="number" min="2" step="1" {...num("deck_count")} /></label>
            <label>Воздушный промежуток, м<input type="number" min="0" step="0.1" {...num("air_gap_m")} /></label>
          </div>
        )}

        <label>Отступ боевика от торца деки, м<input type="number" min="0" step="0.05" {...num("primer_offset_m")} /></label>

        <div className="field-pair">
          <label>Сетка a, м (для q)<input type="number" min="0" step="0.1" {...num("grid_a_m")} /></label>
          <label>Сетка b, м (для q)<input type="number" min="0" step="0.1" {...num("grid_b_m")} /></label>
        </div>

        <button className="calculate-button" onClick={onCalculate} disabled={busy}>
          {busy ? "Считаем заряжание…" : "Рассчитать заряжание"}
        </button>
        <small>Масса заряда считается тем же методом, что и смета — совпадает с ней до килограмма.</small>
      </div>
    </section>
  );
}
