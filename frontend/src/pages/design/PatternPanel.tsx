import { useRef, useState } from "react";
import { api } from "../../api/endpoints";
import type { BlockContour, HoleKind, PatternParams, PatternType, RowPatternParams } from "../../types/design";
import { SELECTABLE_HOLE_KINDS } from "../../types/design";
import { backOffsetDefaultM, isSquarePattern } from "./designParams";
import { RoleBadge } from "./RoleBadge";

const PATTERN_OPTIONS: { value: PatternType; label: string; hint: string }[] = [
  { value: "square", label: "Квадратная", hint: "b = a" },
  { value: "rectangular", label: "Прямоугольная", hint: "a ≠ b, ряды друг под другом" },
  { value: "staggered", label: "Шахматная", hint: "со смещением рядов" },
  { value: "variable", label: "Переменная", hint: "шаг и ЛНС по рядам" },
  { value: "domain_dependent", label: "По доменам", hint: "a/b из геологических доменов" },
];

const KIND_OPTIONS = SELECTABLE_HOLE_KINDS;
// Шаблон «от тыла» генератор строит только у квадратной и прямоугольной сетки
const BACK_ANCHOR_PATTERNS: PatternType[] = ["square", "rectangular"];

function formatNumber(value: number): string {
  return String(Math.round(value * 100) / 100).replace(".", ",");
}
const TAPER_STAGGERED_HINT = "не применяется к шахматной сетке";

function GridPreview({ pattern }: { pattern: PatternType }) {
  const cols = [0, 1, 2];
  const rows = [0, 1, 2];
  return (
    <svg viewBox="0 0 48 48" className="grid-preview" aria-hidden="true">
      {rows.map((row) =>
        cols.map((col) => {
          const shift = (pattern === "staggered" || pattern === "variable") && row % 2 === 1 ? 8 : 0;
          const stepY = pattern === "variable" && row === 0 ? 12 : 16;
          const cx = 8 + col * (pattern === "domain_dependent" && col === 2 ? 12 : 16) + shift;
          const cy = 8 + row * (pattern === "variable" ? stepY : 16);
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
  contour = null,
}: {
  params: PatternParams;
  onChange: (patch: Partial<PatternParams>) => void;
  onGenerate: () => void;
  busy: boolean;
  // Контур блока: по нему «от тыла» ставит азимут рядов
  contour?: BlockContour | null;
}) {
  const [azimuthBusy, setAzimuthBusy] = useState(false);
  // Параметры на момент ответа сервера: правки, сделанные, пока шёл запрос, не перезаписываются
  const paramsRef = useRef(params);
  paramsRef.current = params;
  const anchorAvailable = BACK_ANCHOR_PATTERNS.includes(params.pattern);
  // Сохранённый «от тыла» у другой сетки генератор не применяет — показываем как «от бровки»
  const fromBack = anchorAvailable && params.layout_anchor === "back";
  const hasContour = (contour?.vertices.length ?? 0) >= 3;

  // Азимут тыла с сервера; null — у контура нет несвободной стороны
  async function backAzimuth(): Promise<number | null> {
    if (!contour || !hasContour) return null;
    setAzimuthBusy(true);
    try {
      return (await api.design.backAzimuth(contour)).azimuth_deg;
    } catch {
      return null;
    } finally {
      setAzimuthBusy(false);
    }
  }

  async function selectAnchor(value: string) {
    if (value !== "back") {
      // «От бровки» — ключи убираем, чтобы паспорт не отличался от нетронутого
      onChange({ layout_anchor: undefined, back_offset_m: undefined, back_turn_locked: undefined });
      return;
    }
    const before = paramsRef.current;
    const azimuth = await backAzimuth();
    const now = paramsRef.current;
    if (now !== before) {
      // Пока шёл запрос, параметры поменяли: азимут не трогаем, опору — только если сетка её допускает
      if (BACK_ANCHOR_PATTERNS.includes(now.pattern)) onChange({ layout_anchor: "back" });
      return;
    }
    onChange(azimuth == null ? { layout_anchor: "back" } : { layout_anchor: "back", row_azimuth_deg: azimuth });
  }

  async function azimuthFromBack() {
    const before = paramsRef.current;
    const azimuth = await backAzimuth();
    if (azimuth != null && paramsRef.current === before) onChange({ row_azimuth_deg: azimuth });
  }

  // Сетка без шаблона «от тыла» — ключи опоры убираются, чтобы не попасть в паспорт
  function selectPattern(pattern: PatternType) {
    const stale =
      !BACK_ANCHOR_PATTERNS.includes(pattern) &&
      (params.layout_anchor != null || params.back_offset_m != null || params.back_turn_locked != null);
    onChange(
      stale
        ? { pattern, layout_anchor: undefined, back_offset_m: undefined, back_turn_locked: undefined }
        : { pattern },
    );
  }
  const taperCount = params.front_rows_tilt_count ?? 0;
  // Старые проекты хранят только число рядов — это «Плавный переход»
  const frontScheme: "vertical" | "pair" | "taper" =
    params.front_rows_mode ?? (taperCount > 0 ? "taper" : "vertical");
  // Плавный переход генератор к шахматной сетке не применяет (столбцы через
  // ряд): вариант недоступен, а сохранённый — показывается как неактивный,
  // параметры при этом не переписываются.
  const taperBlocked = params.pattern === "staggered";
  const taperInactive = frontScheme === "taper" && taperBlocked;

  function num<K extends keyof PatternParams>(key: K) {
    return {
      value: params[key] as number,
      onChange: (e: React.ChangeEvent<HTMLInputElement>) =>
        onChange({ [key]: Number(e.target.value) } as Partial<PatternParams>),
    };
  }

  function updateRow(index: number, patch: Partial<RowPatternParams>) {
    const next = params.row_params.map((row, i) => (i === index ? { ...row, ...patch } : row));
    onChange({ row_params: next });
  }

  return (
    <section className="panel">
      <header><b>Раскладка сетки</b><RoleBadge role="designed" /></header>
      <div className="panel-body">
        <div className="pattern-type-grid pattern-type-grid-5">
          {PATTERN_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              className={`pattern-type-option${params.pattern === opt.value ? " active" : ""}`}
              onClick={() => selectPattern(opt.value)}
            >
              <GridPreview pattern={opt.value} />
              <b>{opt.label}</b>
              <small>{opt.hint}</small>
            </button>
          ))}
        </div>

        {anchorAvailable && (
          <div className="field-pair">
            <label title="От бровки — ряды от верхней бровки вглубь. От тыла — приконтурный ряд параллельно тылу (самой длинной несвободной стороне) на линии отрыва (по умолчанию 20·d от него), столбцы к бровке с шагом b, у бровки каждый столбец заканчивается по ЛСП: ничего, наклон или скважина на остатке.">
              Опора сетки
              <select value={fromBack ? "back" : "crest"} onChange={(e) => void selectAnchor(e.target.value)} disabled={azimuthBusy}>
                <option value="crest">От бровки</option>
                <option value="back" disabled={!hasContour}>
                  {hasContour ? "От тыла" : "От тыла (нужен контур блока)"}
                </option>
              </select>
            </label>
            {fromBack && (
              <label title="Расстояние от тыла до приконтурного ряда — линия отрыва. Пусто — 20·d, d — диаметр скважины. Узел берётся в пределах ±0,15·b от отступа, на дуге тыла ряд выходит лесенкой. Подбор раскладки введённый отступ не меняет, а при пустом поле пробует 20·d и 0,5–0,8·b.">
                Отступ от тыла, м
                <input
                  type="number"
                  min="0"
                  step="0.1"
                  value={params.back_offset_m ?? ""}
                  placeholder={formatNumber(backOffsetDefaultM(params.diameter_mm))}
                  onChange={(e) => onChange({ back_offset_m: e.target.value === "" ? undefined : Number(e.target.value) })}
                />
              </label>
            )}
          </div>
        )}
        {anchorAvailable && fromBack && (
          <label
            className="checkbox-row"
            title="Подбор раскладки не поворачивает ряды: пробует только шаблон «от тыла» с азимутом рядов с этой вкладки (при выборе опоры — азимут тыла). Снята — подбор пробует поворот ±5° от тыла и раскладку от бровки."
          >
            <input
              type="checkbox"
              checked={params.back_turn_locked === true}
              onChange={(e) => onChange({ back_turn_locked: e.target.checked ? true : undefined })}
            />
            Без поворота рядов от тыла
          </label>
        )}

        <div className="field-pair">
          <label>Шаг вдоль ряда a, м<input type="number" min="1" step="0.1" {...num("spacing_a_m")} /></label>
          <label>Шаг между рядами b, м
            <input type="number" min="1" step="0.1" {...num("burden_b_m")} disabled={isSquarePattern(params.pattern)} value={isSquarePattern(params.pattern) ? params.spacing_a_m : params.burden_b_m} onChange={num("burden_b_m").onChange} />
          </label>
        </div>

        {params.pattern === "staggered" && (
          <label>Смещение ряда, доля a<input type="number" min="0" max="1" step="0.05" {...num("row_shift_ratio")} /></label>
        )}

        <div className="field-pair">
          <label>Азимут рядов, °<input type="number" min="0" max="359" step="1" {...num("row_azimuth_deg")} /></label>
          {/* «От тыла» ряды идут от тыла: отступ от откоса и ЛНС первого ряда генератор не читает */}
          {!fromBack && (
            <label>Отступ от откоса, м<input type="number" min="0" step="0.1" {...num("offset_from_face_m")} /></label>
          )}
        </div>
        {fromBack && (
          <button
            type="button"
            className="secondary-button"
            onClick={() => void azimuthFromBack()}
            disabled={!hasContour || azimuthBusy}
            title="Азимут рядов — по хорде тыла (самой длинной несвободной стороны контура)."
          >
            Азимут по тылу
          </button>
        )}

        <div className="field-pair">
          {!fromBack && (
          <label>
            ЛНС первого ряда, м
            <input
              type="number"
              min="0"
              step="0.1"
              value={params.first_row_burden_m ?? ""}
              placeholder={String(params.offset_from_face_m)}
              onChange={(e) => onChange({ first_row_burden_m: e.target.value === "" ? null : Number(e.target.value) })}
            />
          </label>
          )}
          {/* Отступ от контура работает в обоих шаблонах: скважины не ближе к любой стороне блока */}
          <label>Отступ от контура, м<input type="number" min="0" step="0.1" {...num("edge_margin_m")} /></label>
        </div>

        {!fromBack && (
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={params.first_row_follow_face}
              onChange={(e) => onChange({ first_row_follow_face: e.target.checked })}
            />
            Первый ряд повторяет открытый откос
          </label>
        )}

        <label>
          Тип скважин основной сетки
          <select value={params.default_kind} onChange={(e) => onChange({ default_kind: e.target.value as HoleKind })}>
            {KIND_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>

        {params.pattern === "variable" && (
          <div className="row-params">
            <small>Параметры по рядам. Последний ряд повторяется дальше вглубь блока.</small>
            {params.row_params.map((row, index) => (
              <div key={index} className="row-params-line">
                <b>{index + 1}</b>
                <input type="number" step="0.1" min="0.5" value={row.spacing_a_m} onChange={(e) => updateRow(index, { spacing_a_m: Number(e.target.value) })} title="a, м" />
                <input type="number" step="0.1" min="0.5" value={row.burden_b_m} onChange={(e) => updateRow(index, { burden_b_m: Number(e.target.value) })} title="b, м" />
                <select value={row.kind} onChange={(e) => updateRow(index, { kind: e.target.value as HoleKind })}>
                  {KIND_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
              </div>
            ))}
            <div className="plans-actions">
              <button type="button" className="secondary-button" onClick={() => onChange({ row_params: [...params.row_params, { spacing_a_m: params.spacing_a_m, burden_b_m: params.burden_b_m, shift_ratio: 0, kind: "production" }] })}>Добавить ряд</button>
              {params.row_params.length > 1 && (
                <button type="button" className="secondary-button" onClick={() => onChange({ row_params: params.row_params.slice(0, -1) })}>Убрать ряд</button>
              )}
            </div>
          </div>
        )}

        {params.pattern === "domain_dependent" && (
          <small>Если у домена заданы шаг и ЛНС, сетка внутри него использует эти значения. Иначе берутся a и b выше.</small>
        )}

        <div className="field-pair">
          <label>Диаметр скважины, мм<input type="number" min="50" step="1" {...num("diameter_mm")} /></label>
          <label>Перебур, м<input type="number" min="0" step="0.1" {...num("subdrill_m")} /></label>
        </div>

        <div className="field-pair">
          <label>Угол от вертикали, °<input type="number" min="0" max="45" step="1" {...num("angle_deg")} /></label>
          <label>Азимут наклона, °<input type="number" min="0" max="359" step="1" {...num("azimuth_deg")} /></label>
        </div>

        <div className="field-pair">
          {!fromBack && (
          <label title="Как поставить скважины первого ряда у откоса: оставить вертикальными, добавить к каждой наклонную на 1 м ближе к откосу или плавно наклонить ряды. Столбцы сетки остаются на одной линии.">
            Первый ряд у откоса
            <select
              value={frontScheme}
              onChange={(e) => {
                const scheme = e.target.value as "vertical" | "pair" | "taper";
                // «Вертикальный» — ключи убираем, чтобы паспорт не отличался от нетронутого
                if (scheme === "vertical")
                  onChange({
                    front_rows_mode: undefined,
                    front_rows_tilt_count: undefined,
                    front_rows_tilt_deg: undefined,
                    min_crest_offset_m: undefined,
                  });
                else if (scheme === "pair") onChange({ front_rows_mode: "pair", front_rows_tilt_count: undefined });
                else onChange({ front_rows_mode: "taper", front_rows_tilt_count: taperCount || 1 });
              }}
            >
              <option value="vertical">Вертикальный</option>
              <option value="pair">Пара: вертикальная + наклонная</option>
              <option value="taper" disabled={taperBlocked}>
                {taperBlocked ? `Плавный переход (${TAPER_STAGGERED_HINT})` : "Плавный переход"}
              </option>
            </select>
          </label>
          )}
          {!fromBack && frontScheme === "taper" && (
            <label title="Сколько первых рядов переходят от наклона к вертикали.">
              Рядов перехода
              <select
                value={taperCount || 1}
                disabled={taperInactive}
                onChange={(e) => onChange({ front_rows_tilt_count: Number(e.target.value) as 1 | 2 })}
              >
                <option value={1}>1</option>
                <option value={2}>2</option>
              </select>
            </label>
          )}
          {!fromBack && frontScheme === "pair" && (
            <label
              className="checkbox-row"
              title="Устье пары сначала сдвигается к кромке; наклон — только если и у кромки ЛСП больше W: наименьший угол до ЛСП ≈ W, не больше 30°."
            >
              <input
                type="checkbox"
                checked={(params.front_rows_tilt_deg ?? 15) > 0}
                // Снят — 0 (без наклона), поставлен — ключ убираем (умолчание сервера).
                onChange={(e) => onChange({ front_rows_tilt_deg: e.target.checked ? undefined : 0 })}
              />
              Разрешить наклон пары
            </label>
          )}
          {(fromBack || frontScheme === "taper") && (
            <label
              title={
                fromBack
                  ? "Наклон последней скважины столбца к откосу, если её ЛСП больше W + 3 %: генератор берёт наименьший угол, при котором ЛСП ≈ W, не больше этого значения (0–30°), а при недоборе поднимает до 30°; 0 — без наклона. Наклон не уводит её от предыдущей у подошвы дальше b + 3 % — иначе ставится скважина на остатке."
                  : "Наибольший наклон от вертикали в сторону откоса, от 0 до 30°."
              }
            >
              {fromBack ? "Предпочтительный наклон, ° от вертикали" : "Наибольший наклон, ° от вертикали"}
              <input
                type="number"
                min="0"
                max="30"
                step="1"
                value={params.front_rows_tilt_deg ?? ""}
                placeholder="15"
                // Пусто — ключ убираем (угол по умолчанию 15°), а не пишем 0
                onChange={(e) =>
                  onChange({
                    front_rows_tilt_deg: e.target.value === "" ? undefined : Math.min(30, Math.max(0, Number(e.target.value))),
                  })
                }
              />
            </label>
          )}
        </div>
        {!fromBack && taperInactive && (
          <small role="note">
            Плавный переход {TAPER_STAGGERED_HINT}: сетка строится с вертикальным первым рядом.
          </small>
        )}

        {/* У вертикального первого ряда отступ генератор не выбирает (это часть 4
            оптимизатора) — поле видно, только если отступ уже задан в паспорте */}
        {(fromBack || frontScheme !== "vertical" || params.min_crest_offset_m != null) && (
          <label title="Устье не ближе этого расстояния к верхней кромке уступа. Пусто — 0,2 м (гусеничный станок; у УРБ задайте больше).">
            Мин. отступ устья от кромки, м
            <input
              type="number"
              min="0"
              step="0.1"
              value={params.min_crest_offset_m ?? ""}
              placeholder="0,2"
              onChange={(e) => onChange({ min_crest_offset_m: e.target.value === "" ? undefined : Number(e.target.value) })}
            />
          </label>
        )}

        <div className="kind-flags">
          <label className="checkbox-row"><input type="checkbox" checked={params.buffer_row} onChange={(e) => onChange({ buffer_row: e.target.checked })} />Буферный ряд</label>
          <label className="checkbox-row"><input type="checkbox" checked={params.trim_row} onChange={(e) => onChange({ trim_row: e.target.checked })} />Оконтуривание</label>
          <label className="checkbox-row"><input type="checkbox" checked={params.presplit_row} onChange={(e) => onChange({ presplit_row: e.target.checked })} />Предщель</label>
          <label className="checkbox-row"><input type="checkbox" checked={params.contour_row} onChange={(e) => onChange({ contour_row: e.target.checked })} />Контурный ряд</label>
          <label className="checkbox-row"><input type="checkbox" checked={params.stab_row} onChange={(e) => onChange({ stab_row: e.target.checked })} />Короткие</label>
          <label className="checkbox-row"><input type="checkbox" checked={params.satellite_holes} onChange={(e) => onChange({ satellite_holes: e.target.checked })} />Сателлиты</label>
          <label className="checkbox-row"><input type="checkbox" checked={params.infill_holes} onChange={(e) => onChange({ infill_holes: e.target.checked })} />Добор в разрывы</label>
        </div>

        {(params.buffer_row || params.stab_row || params.contour_row || params.presplit_row || params.trim_row) && (
          <div className="field-pair">
            {params.buffer_row && <label>Буфер: отступ, м<input type="number" min="0" step="0.1" {...num("buffer_offset_m")} /></label>}
            {params.stab_row && <label title="Глубина вертикальной скважины; у наклонной длина по оси = глубина / cos α.">Глубина коротких (по вертикали), м<input type="number" min="0.5" step="0.1" {...num("stab_depth_m")} /></label>}
            {params.contour_row && <label>Контур: шаг, м<input type="number" min="0.5" step="0.1" {...num("contour_spacing_m")} /></label>}
            {params.presplit_row && <label>Предщель: шаг, м<input type="number" min="0.3" step="0.1" {...num("presplit_spacing_m")} /></label>}
          </div>
        )}

        <button className="calculate-button" onClick={onGenerate} disabled={busy}>
          {busy ? "Строим сетку…" : "Сгенерировать сетку"}
        </button>
        <small>Ручные скважины сохраняются. Устье сажается на кровлю уступа.</small>
      </div>
    </section>
  );
}
