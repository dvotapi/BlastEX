import type { PatternParams, PatternType } from "../../types/design";

const PATTERN_OPTIONS: { value: PatternType; label: string; hint: string }[] = [
  { value: "square", label: "Квадратная", hint: "b = a" },
  { value: "rectangular", label: "Прямоугольная", hint: "a ≠ b, ряды друг под другом" },
  { value: "staggered", label: "Шахматная", hint: "со смещением рядов" },
];

function GridPreview({ pattern }: { pattern: PatternType }) {
  const cols = [0, 1, 2];
  const rows = [0, 1, 2];
  return (
    <svg viewBox="0 0 48 48" className="grid-preview" aria-hidden="true">
      {rows.map((row) =>
        cols.map((col) => {
          const shift = pattern === "staggered" && row % 2 === 1 ? 8 : 0;
          const cx = 8 + col * 16 + shift;
          const cy = 8 + row * 16;
          if (cx > 44) return null;
          return <circle key={`${row}-${col}`} cx={cx} cy={cy} r={3} />;
        }),
      )}
    </svg>
  );
}

export function PatternPanel({
  params,
  onChange,
  onGenerate,
  busy,
}: {
  params: PatternParams;
  onChange: (patch: Partial<PatternParams>) => void;
  onGenerate: () => void;
  busy: boolean;
}) {
  function num(key: keyof PatternParams) {
    return {
      value: params[key] as number,
      onChange: (e: React.ChangeEvent<HTMLInputElement>) => onChange({ [key]: Number(e.target.value) } as Partial<PatternParams>),
    };
  }

  return (
    <section className="panel">
      <header><b>Раскладка сетки</b><span>02</span></header>
      <div className="panel-body">
        <div className="pattern-type-grid">
          {PATTERN_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              className={`pattern-type-option${params.pattern === opt.value ? " active" : ""}`}
              onClick={() => onChange({ pattern: opt.value })}
            >
              <GridPreview pattern={opt.value} />
              <b>{opt.label}</b>
              <small>{opt.hint}</small>
            </button>
          ))}
        </div>

        <div className="field-pair">
          <label>Шаг вдоль ряда a, м<input type="number" min="1" step="0.1" {...num("spacing_a_m")} /></label>
          <label>Шаг между рядами b, м
            <input type="number" min="1" step="0.1" {...num("burden_b_m")} disabled={params.pattern === "square"} value={params.pattern === "square" ? params.spacing_a_m : params.burden_b_m} onChange={num("burden_b_m").onChange} />
          </label>
        </div>

        {params.pattern === "staggered" && (
          <label>Смещение ряда, доля a<input type="number" min="0" max="1" step="0.05" {...num("row_shift_ratio")} /></label>
        )}

        <div className="field-pair">
          <label>Азимут рядов, °<input type="number" min="0" max="359" step="1" {...num("row_azimuth_deg")} /></label>
          <label>Отступ от откоса, м<input type="number" min="0" step="0.1" {...num("offset_from_face_m")} /></label>
        </div>

        <label>Отступ от контура, м<input type="number" min="0" step="0.1" {...num("edge_margin_m")} /></label>

        <div className="field-pair">
          <label>Диаметр скважины, мм<input type="number" min="50" step="1" {...num("diameter_mm")} /></label>
          <label>Перебур, м<input type="number" min="0" step="0.1" {...num("subdrill_m")} /></label>
        </div>

        <div className="field-pair">
          <label>Угол от вертикали, °<input type="number" min="0" max="45" step="1" {...num("angle_deg")} /></label>
          <label>Азимут наклона, °<input type="number" min="0" max="359" step="1" {...num("azimuth_deg")} /></label>
        </div>

        <button className="calculate-button" onClick={onGenerate} disabled={busy}>
          {busy ? "Строим сетку…" : "Сгенерировать сетку"}
        </button>
        <small>Ручные правки скважин сохраняются при повторной генерации.</small>
      </div>
    </section>
  );
}
