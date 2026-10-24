// Панель «Подбор раскладки» (часть 4в): запуск перебора на сервере, ход по
// этапам, три лучших варианта карточками, показ варианта на плане и
// «Применить». Сам опрос — в useLayoutSearch, применение — на странице.
import { ruNumber } from "../../lib/format";
import type { LayoutSearchStage, LayoutSearchState, LayoutSearchStatus, LayoutSearchVariant } from "../../types/design";
import { RoleBadge } from "./RoleBadge";

const STATE_LABELS: Record<LayoutSearchState, string> = {
  idle: "нет подбора",
  running: "идёт",
  done: "готово",
  stopped: "остановлен",
  failed: "ошибка",
};

const STAGE_LABELS: Record<LayoutSearchStage, string> = {
  geometry: "Геометрия сетки",
  front_rows: "Первый ряд у откоса",
  refine: "Уточнение",
};

/** Причины отбраковки варианта: код проверки → человеческий текст. */
const REJECT_LABELS: Record<string, string> = {
  floor_beyond_toe: "забой за подошвой откоса",
  floor_row_gap_excess: "разрыв между рядами у подошвы больше шага",
  collar_too_close_to_crest: "устье ближе допустимого к кромке",
  empty: "сетка не построилась",
};
const UNKNOWN_REJECT = "не прошёл проверку";

const NO_DESIGN_HINT = "Сохраните паспорт, чтобы подобрать раскладку";
// Перебор генерирует сетку из `pattern_params`, а не берёт скважины плана:
// у паспорта, чью сетку правили или строили по другим параметрам, итог с ней не сравним.
const GRID_FROM_PARAMS_HINT =
  "Подбор строит сетку заново по параметрам вкладки „Сетка“: скважины на плане, если их правили или строили по другим параметрам, не учитываются.";
const STALE_TEXT = "Устарел: контур, съёмка или параметры изменились после подбора";
const BOUNDS_CHANGED_TEXT = "Устарел: границы темпа отбойки породы изменились после подбора";
/** Нижняя граница темпа у итогов прежней версии (без сохранённых границ), мс/м. */
const DEFAULT_RELIEF_MIN_MS_M = 3;
const ALL_REJECTED_TEXT = "Ни один вариант не прошёл проверки — показаны лучшие из отбракованных.";
// Остановка — одна пометка: пользователем (state stopped) или концом бюджета
// (done с stopped_early). Без вариантов пометки нет — говорит предупреждение сервера.
const STOPPED_BY_USER_TEXT = "Подбор остановлен — показано лучшее найденное.";
const BUDGET_OVER_TEXT = "Время подбора вышло — показано лучшее найденное.";
const PREPARING_TEXT = "Подготовка…";

function rejectReasons(codes: string[]): string[] {
  return [...new Set(codes.map((code) => REJECT_LABELS[code] ?? UNKNOWN_REJECT))];
}

function numberOf(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** Градусы и мс/м: целые — без дробной части, иначе одна цифра после запятой. */
function plain(value: number): string {
  return ruNumber(value, Number.isInteger(value) ? 0 : 1);
}

function rowsWord(count: number): string {
  const tail = count % 10;
  const tens = count % 100;
  if (tail === 1 && tens !== 11) return "ряд";
  if (tail >= 2 && tail <= 4 && (tens < 12 || tens > 14)) return "ряда";
  return "рядов";
}

/** Схема первого ряда у откоса так же, как её читает генератор сетки. */
function frontRowsText(params: Record<string, unknown>): string {
  const count = numberOf(params.front_rows_tilt_count) ?? 0;
  const mode = params.front_rows_mode ?? (count > 0 ? "taper" : "vertical");
  const tilt = plain(numberOf(params.front_rows_tilt_deg) ?? 15);
  if (mode === "pair") return `пара ${tilt}°`;
  if (mode === "taper") {
    const rows = Math.max(1, count);
    return `переход, ${rows} ${rowsWord(rows)}, ${tilt}°`;
  }
  return "вертикальный";
}

/** Виды сетки со своим шагом b; прочие (нет ключа, «square», неизвестный) — квадрат, b = a, как в генераторе. */
const OWN_BURDEN_PATTERNS: ReadonlySet<unknown> = new Set(["rectangular", "staggered", "variable", "domain_dependent"]);

function stepsRow(params: Record<string, unknown>): [string, string] {
  const a = ruNumber(numberOf(params.spacing_a_m));
  if (!OWN_BURDEN_PATTERNS.has(params.pattern)) return ["Шаг a × a, м", `${a} × ${a}`];
  return ["Шаги a × b, м", `${a} × ${ruNumber(numberOf(params.burden_b_m))}`];
}

function percent(share: number | null): string {
  return share === null ? "—" : String(Math.round(share * 100));
}

function variantRows(
  v: LayoutSearchVariant,
  reliefMinMsM: number,
): { params: [string, string][]; metrics: [string, string][] } {
  const azimuth = numberOf(v.params.row_azimuth_deg);
  return {
    params: [
      ["Азимут рядов, °", azimuth === null ? "—" : plain(azimuth)],
      stepsRow(v.params),
      ["Первый ряд", frontRowsText(v.params)],
      ["Вруб у фланга", v.cut_flank === "right" ? "правого" : "левого"],
    ],
    metrics: [
      ["ЛСП вне коридора", String(v.lsp_out)],
      [`Быстрее ${plain(reliefMinMsM)} мс/м, %`, percent(v.fast_share)],
      ["Стыки фронтов, м", ruNumber(v.converging_length_m, 1)],
      ["Вне коридора ±25 %, %", percent(v.outside_share)],
      ["Разброс темпа", ruNumber(v.robust_spread, 2)],
      ["Скважин", String(v.hole_count)],
      ["В окне 8 мс (справочно)", String(v.window8_max_holes)],
      ["Замедление в скважине, мс", ruNumber(v.downhole_ms, 0)],
    ],
  };
}

function Rows({ rows }: { rows: [string, string][] }) {
  return (
    <dl className="layout-variant-rows">
      {rows.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function LayoutSearchPanel({
  designId,
  status,
  stale,
  error,
  manualCount,
  locked,
  previewIndex,
  onStart,
  onStop,
  onPreview,
  onApply,
}: {
  designId: string | null;
  status: LayoutSearchStatus | null;
  /** Результат посчитан по другим входам, чем сейчас, или границы темпа породы сменились. */
  stale: boolean;
  /** Ошибка запроса (запуск занят, сеть). */
  error: string | null;
  /** Ручных скважин в блоке: применение их заменит. */
  manualCount: number;
  /** Проектную часть паспорта править нельзя (статус «утверждён» и дальше). */
  locked: boolean;
  previewIndex: number | null;
  onStart: () => void;
  onStop: () => void;
  onPreview: (index: number | null) => void;
  onApply: (variant: LayoutSearchVariant) => void;
}) {
  const running = status?.state === "running";
  const result = running ? null : status?.result ?? null;
  const stopMark =
    result?.stopped_early && result.best.length > 0
      ? status?.state === "stopped"
        ? STOPPED_BY_USER_TEXT
        : BUDGET_OVER_TEXT
      : null;

  // Нижняя граница темпа, с которой шёл подбор: по ней считана доля быстрых.
  const reliefMinMsM = numberOf(result?.relief_min_ms_m) ?? DEFAULT_RELIEF_MIN_MS_M;
  const staleText = status?.bounds_changed ? BOUNDS_CHANGED_TEXT : STALE_TEXT;

  function apply(variant: LayoutSearchVariant) {
    if (manualCount > 0 && !window.confirm(`Ручные правки (${manualCount}) будут потеряны. Применить вариант?`)) return;
    if (stale && !window.confirm(`${staleText}. Применить вариант?`)) return;
    onApply(variant);
  }

  function togglePreview(index: number) {
    onPreview(previewIndex === index ? null : index);
  }

  return (
    <section className="panel layout-search">
      <header><b>Подбор раскладки</b><RoleBadge role="designed" /></header>
      <div className="panel-body">
        <button
          type="button"
          className="calculate-button"
          onClick={onStart}
          disabled={locked || designId === null || running}
          title={designId === null ? NO_DESIGN_HINT : undefined}
        >
          Подобрать раскладку
        </button>
        {designId === null && <small>{NO_DESIGN_HINT}</small>}
        <small>{GRID_FROM_PARAMS_HINT}</small>
        {error && <small role="alert" className="frag-warnings">{error}</small>}

        {/* «Остановлен» говорит пометка результата — строка состояния её не повторяет. */}
        {status && status.state !== "idle" && status.state !== "stopped" && (
          <small className="layout-search-state">Подбор: {STATE_LABELS[status.state]}</small>
        )}
        {status?.state === "failed" && status.error && <small className="frag-warnings">{status.error}</small>}

        {running && status && (
          <div className="layout-search-progress">
            <progress value={status.done} max={Math.max(status.total, 1)} />
            <span>
              {status.total > 0
                ? `${status.stage ? `${STAGE_LABELS[status.stage]}: ` : ""}${status.done} из ${status.total}`
                : PREPARING_TEXT}
            </span>
            <small>Прошло {ruNumber(status.elapsed_s ?? 0, 0)} с</small>
            <button type="button" className="secondary-button" onClick={onStop}>Остановить</button>
          </div>
        )}

        {result && (
          <>
            {(stale || result.all_rejected || stopMark || result.warnings.length > 0) && (
              <ul className="frag-warnings layout-search-marks">
                {stale && <li>{staleText}</li>}
                {result.all_rejected && <li>{ALL_REJECTED_TEXT}</li>}
                {stopMark && <li>{stopMark}</li>}
                {result.warnings.map((text, i) => <li key={i}>{text}</li>)}
              </ul>
            )}
            <div className="layout-variant-list">
              {result.best.map((variant, index) => {
                const rows = variantRows(variant, reliefMinMsM);
                const shown = previewIndex === index;
                return (
                  <article
                    key={index}
                    className={`layout-variant-card${shown ? " active" : ""}${variant.rejected ? " rejected" : ""}`}
                  >
                    {/* Заголовок — кнопка показа на плане; повторное нажатие снимает показ. */}
                    <button
                      type="button"
                      className="layout-variant-toggle"
                      aria-pressed={shown}
                      title={shown ? "Убрать с плана" : "Показать на плане"}
                      onClick={() => togglePreview(index)}
                    >
                      Вариант {index + 1}
                    </button>
                    {variant.rejected && (
                      <div className="frag-warnings">
                        <small>не прошёл проверки</small>
                        <ul>
                          {rejectReasons(variant.reject_codes).map((reason) => <li key={reason}>{reason}</li>)}
                        </ul>
                      </div>
                    )}
                    <Rows rows={rows.params} />
                    <Rows rows={rows.metrics} />
                    <div className="layout-variant-actions">
                      {shown && (
                        <button type="button" className="secondary-button" onClick={() => onPreview(null)}>
                          Скрыть
                        </button>
                      )}
                      <button
                        type="button"
                        className="secondary-button"
                        disabled={locked}
                        onClick={() => apply(variant)}
                      >
                        Применить
                      </button>
                    </div>
                  </article>
                );
              })}
            </div>
          </>
        )}
      </div>
    </section>
  );
}
