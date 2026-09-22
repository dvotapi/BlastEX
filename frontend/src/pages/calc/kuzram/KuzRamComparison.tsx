import { ruNumber } from "../../../lib/format";
import type { BlastVariant } from "../../../types";
import { ThresholdFlag } from "./ThresholdFlag";
import { formatOversize, formatQ, gridText, LEGACY_Q_MAX_KG_M3, LEGACY_Q_MIN_KG_M3, Q_MIN_KG_M3, qDeltaText, trimmed } from "./kuzramFormat";
import { BURDEN_TO_DIAMETER_WARN_ABOVE } from "./kuzramSettings";

/** Результат одной модели в строке — чтобы сводка и таблица рисовали обе модели одинаково. */
type ModelResult = {
  q: number;
  qFloor: number;
  gridA: number;
  gridB: number;
  x50: number;
  n: number;
  oversize: number;
  reached: boolean;
  /** «До исправления» — у «!» здесь другой совет: верхняя граница перебора там фиксирована. */
  legacy: boolean;
};

function kuzramResult(variant: BlastVariant): ModelResult {
  return {
    q: variant.specific_q_kg_m3,
    qFloor: Q_MIN_KG_M3,
    gridA: variant.grid_a_m,
    gridB: variant.grid_b_m,
    x50: variant.x50_mm,
    n: variant.details.uniformity_n,
    oversize: variant.oversize_pct,
    reached: variant.reached,
    legacy: false,
  };
}

function legacyResult(variant: BlastVariant): ModelResult {
  const legacy = variant.legacy;
  return {
    q: legacy.specific_q_kg_m3,
    qFloor: LEGACY_Q_MIN_KG_M3,
    gridA: legacy.grid_a_m,
    gridB: legacy.grid_b_m,
    x50: legacy.x50_mm,
    n: legacy.details.uniformity_n,
    oversize: legacy.oversize_pct,
    reached: legacy.reached,
    legacy: true,
  };
}

/** Заголовок «!»: у «до исправления» граница перебора фиксирована и от окна
 * настроек не зависит — совет поднять её там был бы неверным. */
const LEGACY_THRESHOLD_TITLE =
  `Порог негабарита не достигнут: q на верхней границе прежнего перебора (${ruNumber(LEGACY_Q_MAX_KG_M3, 2)} кг/м³).`;

function QValue({ result }: { result: ModelResult }) {
  return (
    <>
      {!result.reached && <ThresholdFlag title={result.legacy ? LEGACY_THRESHOLD_TITLE : undefined} />}
      {formatQ(result.q, ",", result.qFloor)}
    </>
  );
}

function Stat({ title, tone, result, thresholdPct }: { title: string; tone: "new" | "legacy"; result: ModelResult; thresholdPct: number }) {
  return (
    <div className="kuzram-stat">
      <span className="kuzram-stat-title">
        <i className={tone} aria-hidden="true" />
        {title}
      </span>
      <span>
        <b className="kuzram-stat-q">
          <QValue result={result} />
        </b>{" "}
        <small>кг/м³</small>
      </span>
      <span className="kuzram-stat-line">
        сетка {gridText(result.gridA, result.gridB)} м · негабарит {formatOversize(result.oversize, result.reached, thresholdPct)} %
      </span>
    </div>
  );
}

function ModelCells({ result, thresholdPct }: { result: ModelResult; thresholdPct: number }) {
  return (
    <>
      <td className="sep">
        <QValue result={result} />
      </td>
      <td>{gridText(result.gridA, result.gridB)}</td>
      <td>{ruNumber(result.x50, 1)}</td>
      <td>{ruNumber(result.n, 2)}</td>
      <td>{formatOversize(result.oversize, result.reached, thresholdPct)}</td>
    </>
  );
}

const MODEL_COLUMNS = ["q, кг/м³", "Сетка a × b, м", "x50, мм", "n", "Негабарит, %"];

/**
 * Сводка выбранной коронки и таблица по коронкам: Kuz-Ram рядом с расчётом
 * «до исправления». Выбор строки — тот же, что в таблице листа.
 */
export function KuzRamComparison({
  variants,
  selectedIndex,
  onSelect,
  thresholdPct,
}: {
  variants: BlastVariant[];
  selectedIndex: number;
  onSelect: (index: number) => void;
  thresholdPct: number;
}) {
  if (!variants.length) {
    return <p className="kuzram-empty">Нет расчёта: задайте исходные данные на листе и нажмите «Рассчитать варианты».</p>;
  }
  const selected = variants[selectedIndex] ?? variants[0];
  const wide = variants.filter((variant) => variant.details.burden_to_diameter > BURDEN_TO_DIAMETER_WARN_ABOVE);

  return (
    <>
      <section className="kuzram-card" aria-labelledby="kuzram-summary-title">
        <h3 id="kuzram-summary-title">Коронка {trimmed(selected.crown_mm)} мм</h3>
        <div className="kuzram-summary">
          <Stat title="Kuz-Ram" tone="new" result={kuzramResult(selected)} thresholdPct={thresholdPct} />
          <Stat title="До исправления" tone="legacy" result={legacyResult(selected)} thresholdPct={thresholdPct} />
          <div className="kuzram-stat">
            <span className="kuzram-stat-title">Разница q</span>
            <b className="kuzram-stat-q">{qDeltaText(selected.specific_q_kg_m3, selected.legacy.specific_q_kg_m3)}</b>
            <span className="kuzram-stat-line">Kuz-Ram относительно «до исправления»</span>
          </div>
        </div>
      </section>

      <section className="kuzram-card" aria-labelledby="kuzram-table-title">
        <h3 id="kuzram-table-title">Варианты сетки</h3>
        <div className="kuzram-table-scroll">
          <table className="kuzram-table">
            <caption>Строка на коронку; выбор строки меняет выбранную коронку и на листе. «!» — порог негабарита не достигнут.</caption>
            <thead>
              <tr className="groups">
                <th aria-hidden="true" />
                <th colSpan={5} scope="colgroup" className="sep g-new">Kuz-Ram</th>
                <th colSpan={5} scope="colgroup" className="sep g-legacy">До исправления</th>
                <th aria-hidden="true" className="sep" />
              </tr>
              <tr>
                <th scope="col">Коронка, мм</th>
                {["new", "legacy"].map((model) =>
                  MODEL_COLUMNS.map((title, index) => (
                    <th key={`${model}-${title}`} scope="col" className={index === 0 ? "sep" : undefined}>
                      {title}
                    </th>
                  )),
                )}
                <th scope="col" className="sep">Разница q</th>
              </tr>
            </thead>
            <tbody>
              {variants.map((variant, index) => (
                <tr
                  key={variant.crown_mm}
                  aria-selected={index === selectedIndex}
                  tabIndex={0}
                  onClick={() => onSelect(index)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onSelect(index);
                    }
                  }}
                >
                  <td>{trimmed(variant.crown_mm)}</td>
                  <ModelCells result={kuzramResult(variant)} thresholdPct={thresholdPct} />
                  <ModelCells result={legacyResult(variant)} thresholdPct={thresholdPct} />
                  <td className="sep">{qDeltaText(variant.specific_q_kg_m3, variant.legacy.specific_q_kg_m3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {wide.length > 0 && (
          <p className="kuzram-warning">
            W/d выше {BURDEN_TO_DIAMETER_WARN_ABOVE} у коронок {wide.map((variant) => trimmed(variant.crown_mm)).join(", ")} мм —
            сетка редкая для диаметра: Каннингем рекомендует 25–35. Подробности — в разборе расчёта.
          </p>
        )}
      </section>
    </>
  );
}
