import { useMemo, useState } from "react";
import { ruNumber } from "../../lib/format";
import type {
  BlastResult,
  BlastResultCompareResponse,
  ComparisonRow,
  DesignedBackbreak,
  DesignedMuckpile,
  DesignCostResult,
  FragmentationPredictResponse,
  VibrationPredictResponse,
} from "../../types/design";
import {
  TOE_CONDITION_LABELS,
  emptyBlastResult,
  emptyFlyrock,
} from "../../types/design";
import { RoleBadge } from "./RoleBadge";

function Metric({ label, value, unit, digits, warn }: { label: string; value: number | null; unit: string; digits: number; warn?: boolean }) {
  return (
    <div className={warn ? "vib-warn-metric" : undefined}>
      <span>{label}</span>
      <strong>{ruNumber(value, digits)}</strong>
      <small>{unit}</small>
    </div>
  );
}

function numOrEmpty(value: number | null | undefined): string {
  return value === null || value === undefined ? "" : String(value);
}

function parseOpt(raw: string): number | null {
  if (raw.trim() === "") return null;
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
}

function cell(value: number | string | null | undefined, digits = 1): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "string") return value;
  return ruNumber(value, digits);
}

function deltaClass(value: number | null | undefined, limit: number): string {
  if (value === null || value === undefined) return "";
  return Math.abs(value) > limit ? " over" : "";
}

export function PostBlastPanel({
  designId,
  stored,
  fragResult,
  vibResult,
  costResult,
  lumpSizeMm,
  onRecord,
  onCompare,
  onClear,
  busy,
  result,
  locked = false,
}: {
  designId: string;
  stored: BlastResult | null;
  fragResult: FragmentationPredictResponse | null;
  vibResult: VibrationPredictResponse | null;
  costResult: DesignCostResult | null;
  lumpSizeMm: number;
  onRecord: (item: BlastResult, extras: {
    predicted_fragmentation: FragmentationPredictResponse["site"]["prediction"] | null;
    predicted_vibration: Array<{ receptor_id: string; ppv_mm_s: number; frequency_hz: number | null; receptor_name: string; role: "predicted" }>;
    planned_cost: {
      role: "designed";
      total_amount_rub: number | null;
      cost_per_m3: number | null;
      variable_total_rub: number | null;
      labor_total_rub: number | null;
      fixed_total_rub: number | null;
      secondary_breaking_rub: number | null;
      notes: string;
    } | null;
    designed_fragmentation: { role: "designed"; lump_size_mm: number; max_oversize_pct: number } | null;
    designed_muckpile: DesignedMuckpile | null;
    designed_backbreak: DesignedBackbreak | null;
    designed_toe_condition: string;
  }) => void;
  onCompare: () => void;
  onClear: () => void;
  busy: boolean;
  result: BlastResultCompareResponse | null;
  locked?: boolean;
}) {
  const draft = useMemo(() => stored ?? emptyBlastResult(designId), [stored, designId]);
  const [form, setForm] = useState<BlastResult | null>(null);
  const current = form ?? draft;
  const [designedMuck, setDesignedMuck] = useState<DesignedMuckpile>({
    role: "designed",
    length_m: stored?.basis?.designed_muckpile?.length_m ?? null,
    width_m: stored?.basis?.designed_muckpile?.width_m ?? null,
    height_m: stored?.basis?.designed_muckpile?.height_m ?? null,
    volume_m3: stored?.basis?.designed_muckpile?.volume_m3 ?? null,
    throw_m: stored?.basis?.designed_muckpile?.throw_m ?? null,
    notes: "",
  });
  const [designedBackbreak, setDesignedBackbreak] = useState<DesignedBackbreak>({
    role: "designed",
    max_m: stored?.basis?.designed_backbreak?.max_m ?? null,
    mean_m: stored?.basis?.designed_backbreak?.mean_m ?? null,
    crest_loss_m: stored?.basis?.designed_backbreak?.crest_loss_m ?? null,
    notes: "",
  });
  const [designedToe, setDesignedToe] = useState(stored?.basis?.designed_toe_condition || "clean");

  function patch(next: Partial<BlastResult>) {
    setForm({ ...current, ...next, role: "measured" });
  }

  function recordCurrent() {
    const predictedVibration = (vibResult?.predictions ?? []).map((row) => ({
      receptor_id: row.receptor_id,
      ppv_mm_s: row.ppv_mm_s,
      frequency_hz: null,
      receptor_name: row.receptor_name,
      role: "predicted" as const,
    }));
    onRecord(
      { ...current, design_id: designId, role: "measured" },
      {
        predicted_fragmentation: fragResult?.site.prediction ?? stored?.basis?.predicted_fragmentation ?? null,
        predicted_vibration: predictedVibration.length ? predictedVibration : (stored?.basis?.predicted_vibration ?? []),
        planned_cost: costResult
          ? {
              role: "designed",
              total_amount_rub: costResult.total_amount_rub,
              cost_per_m3: costResult.cost_per_m3,
              variable_total_rub: costResult.variable_total_rub,
              labor_total_rub: costResult.labor_total_rub,
              fixed_total_rub: costResult.fixed_total_rub,
              secondary_breaking_rub: current.secondary_breaking?.cost_rub ?? null,
              notes: "",
            }
          : stored?.basis?.planned_cost ?? null,
        designed_fragmentation: fragResult?.target ?? stored?.basis?.designed_fragmentation ?? {
          role: "designed",
          lump_size_mm: lumpSizeMm,
          max_oversize_pct: 5,
        },
        designed_muckpile: designedMuck,
        designed_backbreak: designedBackbreak,
        designed_toe_condition: designedToe,
      },
    );
    setForm(null);
  }

  const frag = current.fragmentation;
  const vib = current.vibration;
  const muck = current.muckpile;
  const backbreak = current.backbreak;
  const toe = current.toe_condition;
  const flyrock = current.flyrock_observations[0] ?? emptyFlyrock();
  const secondary = current.secondary_breaking;
  const cost = current.cost_actual;

  return (
    <section className="panel">
      <header><b>После взрыва</b><RoleBadge role="measured" /></header>
      <div className="panel-body">
        <small>
          Измерения не переписывают прогноз и проект. Сравнение: прогноз ↔ замер, проект ↔ факт, смета ↔ факт.
        </small>

        <b>Кусковатость (P20 / P50 / P80)</b>
        <div className="field-pair">
          <label>P20, мм
            <input type="number" step="1" min="0" value={numOrEmpty(frag?.x20_mm)} onChange={(e) => patch({ fragmentation: { ...frag!, x20_mm: parseOpt(e.target.value), role: "measured" } })} />
          </label>
          <label>P50, мм
            <input type="number" step="1" min="0" value={numOrEmpty(frag?.x50_mm)} onChange={(e) => patch({ fragmentation: { ...frag!, x50_mm: parseOpt(e.target.value), role: "measured" } })} />
          </label>
        </div>
        <div className="field-pair">
          <label>P80, мм
            <input type="number" step="1" min="0" value={numOrEmpty(frag?.x80_mm)} onChange={(e) => patch({ fragmentation: { ...frag!, x80_mm: parseOpt(e.target.value), role: "measured" } })} />
          </label>
          <label>Негабарит, %
            <input type="number" step="0.1" min="0" value={numOrEmpty(frag?.oversize_pct)} onChange={(e) => patch({ fragmentation: { ...frag!, oversize_pct: parseOpt(e.target.value), role: "measured" } })} />
          </label>
        </div>
        <label>Источник / метод
          <input type="text" value={`${frag?.source || ""}${frag?.method ? ` / ${frag.method}` : ""}`} onChange={(e) => {
            const [source, ...rest] = e.target.value.split("/");
            patch({ fragmentation: { ...frag!, source: source.trim(), method: rest.join("/").trim(), role: "measured" } });
          }} />
        </label>

        <b>Сейсмика</b>
        <div className="field-pair">
          <label>PPV, мм/с
            <input type="number" step="0.01" min="0" value={numOrEmpty(vib?.ppv_mm_s)} onChange={(e) => patch({ vibration: { ...vib!, ppv_mm_s: parseOpt(e.target.value), role: "measured" } })} />
          </label>
          <label>Частота, Гц
            <input type="number" step="0.1" min="0" value={numOrEmpty(vib?.frequency_hz)} onChange={(e) => patch({ vibration: { ...vib!, frequency_hz: parseOpt(e.target.value), role: "measured" } })} />
          </label>
        </div>
        <label>Рецептор
          <input type="text" value={vib?.receptor_id ?? ""} onChange={(e) => patch({ vibration: { ...vib!, receptor_id: e.target.value, role: "measured" } })} />
        </label>

        <b>Развал</b>
        <div className="field-pair">
          <label>Длина факт, м
            <input type="number" step="0.1" min="0" value={numOrEmpty(muck?.length_m)} onChange={(e) => patch({ muckpile: { ...muck!, length_m: parseOpt(e.target.value), role: "measured" } })} />
          </label>
          <label>Длина проект, м
            <input type="number" step="0.1" min="0" value={numOrEmpty(designedMuck.length_m)} onChange={(e) => setDesignedMuck({ ...designedMuck, length_m: parseOpt(e.target.value) })} />
          </label>
        </div>
        <div className="field-pair">
          <label>Ширина факт, м
            <input type="number" step="0.1" min="0" value={numOrEmpty(muck?.width_m)} onChange={(e) => patch({ muckpile: { ...muck!, width_m: parseOpt(e.target.value), role: "measured" } })} />
          </label>
          <label>Высота факт, м
            <input type="number" step="0.1" min="0" value={numOrEmpty(muck?.height_m)} onChange={(e) => patch({ muckpile: { ...muck!, height_m: parseOpt(e.target.value), role: "measured" } })} />
          </label>
        </div>
        <div className="field-pair">
          <label>Объём факт, м³
            <input type="number" step="1" min="0" value={numOrEmpty(muck?.volume_m3)} onChange={(e) => patch({ muckpile: { ...muck!, volume_m3: parseOpt(e.target.value), role: "measured" } })} />
          </label>
          <label>Отброс факт, м
            <input type="number" step="0.1" min="0" value={numOrEmpty(muck?.throw_m)} onChange={(e) => patch({ muckpile: { ...muck!, throw_m: parseOpt(e.target.value), role: "measured" } })} />
          </label>
        </div>

        <b>Вывал и забой</b>
        <div className="field-pair">
          <label>Вывал факт, м
            <input type="number" step="0.01" min="0" value={numOrEmpty(backbreak?.max_m)} onChange={(e) => patch({ backbreak: { ...backbreak!, max_m: parseOpt(e.target.value), role: "measured" } })} />
          </label>
          <label>Вывал проект, м
            <input type="number" step="0.01" min="0" value={numOrEmpty(designedBackbreak.max_m)} onChange={(e) => setDesignedBackbreak({ ...designedBackbreak, max_m: parseOpt(e.target.value) })} />
          </label>
        </div>
        <div className="field-pair">
          <label>Забой факт
            <select value={toe?.condition || "clean"} onChange={(e) => patch({ toe_condition: { ...toe!, condition: e.target.value, role: "measured" } })}>
              {Object.entries(TOE_CONDITION_LABELS).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </label>
          <label>Забой проект
            <select value={designedToe} onChange={(e) => setDesignedToe(e.target.value)}>
              {Object.entries(TOE_CONDITION_LABELS).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </label>
        </div>
        <label>Остаток на почве, м
          <input type="number" step="0.01" min="0" value={numOrEmpty(toe?.leftover_height_m)} onChange={(e) => patch({ toe_condition: { ...toe!, leftover_height_m: parseOpt(e.target.value), role: "measured" } })} />
        </label>

        <b>Разлёт и вторичка</b>
        <div className="field-pair">
          <label>Разлёт, м
            <input type="number" step="1" min="0" value={numOrEmpty(flyrock.max_range_m)} onChange={(e) => patch({ flyrock_observations: [{ ...flyrock, max_range_m: parseOpt(e.target.value), role: "measured" }] })} />
          </label>
          <label>Кусков разлёта
            <input type="number" step="1" min="0" value={numOrEmpty(flyrock.count)} onChange={(e) => patch({ flyrock_observations: [{ ...flyrock, count: parseOpt(e.target.value), role: "measured" }] })} />
          </label>
        </div>
        <div className="field-pair">
          <label>Вторичка, м³
            <input type="number" step="1" min="0" value={numOrEmpty(secondary?.volume_m3)} onChange={(e) => patch({ secondary_breaking: { ...secondary!, volume_m3: parseOpt(e.target.value), role: "measured" } })} />
          </label>
          <label>Стоимость вторички, ₽
            <input type="number" step="1" min="0" value={numOrEmpty(secondary?.cost_rub)} onChange={(e) => patch({
              secondary_breaking: { ...secondary!, cost_rub: parseOpt(e.target.value), role: "measured" },
              cost_actual: { ...cost!, secondary_breaking_rub: parseOpt(e.target.value), role: "measured" },
            })} />
          </label>
        </div>

        <b>Фактическая стоимость</b>
        <div className="field-pair">
          <label>Итого факт, ₽
            <input type="number" step="1" min="0" value={numOrEmpty(cost?.total_amount_rub)} onChange={(e) => patch({ cost_actual: { ...cost!, total_amount_rub: parseOpt(e.target.value), role: "measured" } })} />
          </label>
          <label>₽/м³ факт
            <input type="number" step="0.1" min="0" value={numOrEmpty(cost?.cost_per_m3)} onChange={(e) => patch({ cost_actual: { ...cost!, cost_per_m3: parseOpt(e.target.value), role: "measured" } })} />
          </label>
        </div>

        <div className="plans-actions">
          <button type="button" className="calculate-button" onClick={recordCurrent} disabled={busy || locked}>
            {busy ? "Пишем…" : "Записать результаты"}
          </button>
          {stored && (
            <button type="button" className="ghost-button" onClick={onClear} disabled={locked}>Очистить</button>
          )}
        </div>
        <button type="button" className="secondary-button" onClick={onCompare} disabled={busy || !stored}>
          {busy ? "Считаем…" : "Сравнить прогноз и проект"}
        </button>

        {result?.has_result && (
          <>
            <div className="metrics-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
              <Metric label="Строк прогноз↔замер" value={result.predicted_vs_measured.length} unit="" digits={0} />
              <Metric label="Строк проект↔факт" value={result.designed_vs_actual.length} unit="" digits={0} />
            </div>
            {result.warnings.length > 0 && (
              <small className="frag-warnings">{result.warnings.slice(0, 4).join(" ")}</small>
            )}
            <ComparisonTable title="Прогноз ↔ измерение" rows={result.predicted_vs_measured} mode="predicted" />
            <ComparisonTable title="Проект ↔ факт" rows={result.designed_vs_actual} mode="designed" />
            <ComparisonTable title="Смета ↔ факт" rows={result.planned_vs_actual_cost} mode="cost" />
          </>
        )}
      </div>
    </section>
  );
}

function ComparisonTable({
  title,
  rows,
  mode,
}: {
  title: string;
  rows: ComparisonRow[];
  mode: "predicted" | "designed" | "cost";
}) {
  const visible = rows.filter((row) => {
    if (mode === "predicted") return row.predicted !== null || row.measured !== null;
    return row.designed !== null || row.actual !== null || row.measured !== null;
  });
  if (!visible.length) return null;
  const left = mode === "predicted" ? "Прогноз" : mode === "cost" ? "План" : "Проект";
  const right = mode === "predicted" ? "Замер" : "Факт";
  return (
    <div className="post-blast-table">
      <b>{title}</b>
      <div className="post-blast-head">
        <span>Показатель</span>
        <span>{left}</span>
        <span>{right}</span>
        <span>Δ</span>
      </div>
      {visible.map((row) => {
        const leftValue = mode === "predicted" ? row.predicted : row.designed;
        const rightValue = mode === "predicted" ? row.measured : (row.actual ?? row.measured);
        const delta = mode === "predicted" ? row.measured_minus_predicted : row.actual_minus_designed;
        const leftText = row.designed_label && mode !== "predicted" ? row.designed_label : cell(leftValue, row.unit === "₽" ? 0 : 1);
        const rightText = row.actual_label && mode !== "predicted" ? row.actual_label : cell(rightValue, row.unit === "₽" ? 0 : 1);
        return (
          <div key={`${row.metric}-${row.receptor_id || ""}-${row.label}`} className={`post-blast-row${deltaClass(typeof delta === "number" ? delta : null, row.unit === "%" ? 5 : 0)}${row.mismatch ? " over" : ""}`}>
            <span>{row.label}{row.unit ? `, ${row.unit}` : ""}</span>
            <b>{leftText}</b>
            <b>{rightText}</b>
            <b>{row.mismatch ? "≠" : cell(delta, row.unit === "₽" ? 0 : 1)}</b>
          </div>
        );
      })}
    </div>
  );
}
