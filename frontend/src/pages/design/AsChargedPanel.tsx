import { useMemo, useState } from "react";
import { ruNumber } from "../../lib/format";
import type {
  AsChargedCompareResponse,
  AsChargedHole,
  ChargeDeviation,
  Deck,
  Hole,
  HoleLoad,
} from "../../types/design";
import { AS_CHARGED_METRIC_LABELS, DECK_KIND_LABELS, emptyAsCharged } from "../../types/design";

function Metric({ label, value, unit, digits, warn }: { label: string; value: number | null; unit: string; digits: number; warn?: boolean }) {
  return (
    <div className={warn ? "vib-warn-metric" : undefined}>
      <span>{label}</span>
      <strong>{ruNumber(value, digits)}</strong>
      <small>{unit}</small>
    </div>
  );
}

function warnAbs(value: number | null, limit: number): boolean {
  return value !== null && Math.abs(value) > limit;
}

function emptyDeck(): Deck {
  return { kind: "bulk_explosive", from_m: 0, to_m: 0, explosive_key: "", mass_kg: 0, product: "" };
}

export function AsChargedPanel({
  holes,
  loads,
  asCharged,
  selectedHoleId,
  onSelectedHoleIdChange,
  onRecord,
  onDelete,
  onCompare,
  busy,
  result,
  explosiveKey,
}: {
  holes: Hole[];
  loads: HoleLoad[];
  asCharged: AsChargedHole[];
  selectedHoleId: string | null;
  onSelectedHoleIdChange: (id: string | null) => void;
  onRecord: (item: AsChargedHole) => void;
  onDelete: (designHoleId: string) => void;
  onCompare: () => void;
  busy: boolean;
  result: AsChargedCompareResponse | null;
  explosiveKey: string;
}) {
  const selectedDesigned = holes.find((hole) => hole.id === selectedHoleId) ?? null;
  const selectedLoad = loads.find((load) => load.hole_id === selectedHoleId) ?? null;
  const selectedExecuted = asCharged.find((item) => item.design_hole_id === selectedHoleId) ?? null;
  const draft = useMemo(
    () => (selectedExecuted ? selectedExecuted : selectedHoleId ? emptyAsCharged(selectedLoad, selectedHoleId, explosiveKey) : null),
    [selectedExecuted, selectedLoad, selectedHoleId, explosiveKey],
  );
  const [form, setForm] = useState<AsChargedHole | null>(null);
  const current = form && form.design_hole_id === selectedHoleId ? form : draft;
  const selectedDeviation = result?.deviations.find((row) => row.design_hole_id === selectedHoleId) ?? null;

  function patch(next: Partial<AsChargedHole>) {
    if (!current) return;
    setForm({ ...current, ...next, role: "executed" });
  }

  function patchDeck(index: number, next: Partial<Deck>) {
    if (!current) return;
    patch({ decks: current.decks.map((deck, i) => (i === index ? { ...deck, ...next } : deck)) });
  }

  function recordCurrent() {
    if (!current) return;
    const primers = current.primer_items.map((item) => item.position_m);
    onRecord({ ...current, primers, role: "executed" });
    setForm(null);
  }

  return (
    <section className="panel">
      <header><b>Факт заряжания</b><span>11</span></header>
      <div className="panel-body">
        <small>
          Проектный заряд не меняется. Здесь — фактический продукт, масса, деки, забойка, боевик и время заряжания.
        </small>

        <div className="geology-list">
          {asCharged.length === 0 && (
            <div className="surface-card empty"><b>Факта нет</b><small>выберите скважину и запишите заряд</small></div>
          )}
          {asCharged.map((item) => {
            const row = result?.deviations.find((dev) => dev.design_hole_id === item.design_hole_id);
            return (
              <button
                key={item.design_hole_id}
                type="button"
                className={`geology-card${item.design_hole_id === selectedHoleId ? " active" : ""}`}
                onClick={() => {
                  onSelectedHoleIdChange(item.design_hole_id);
                  setForm(null);
                }}
              >
                <i className="as-charged-swatch" />
                <div>
                  <b>{item.design_hole_id}</b>
                  <small>
                    {row
                      ? `Δ ${ruNumber(row.charge_mass_delta_kg, 1)} кг`
                      : `${ruNumber(item.charge_mass_kg, 1)} кг`}
                  </small>
                </div>
              </button>
            );
          })}
        </div>

        {selectedDesigned && current && (
          <>
            <small>Проект {selectedDesigned.id} не меняется. Ниже — только факт.</small>
            <div className="field-pair">
              <label>Продукт ВВ
                <input type="text" value={current.explosive_product} onChange={(e) => patch({ explosive_product: e.target.value })} />
              </label>
              <label>Масса заряда, кг
                <input type="number" step="0.1" min="0" value={current.charge_mass_kg} onChange={(e) => patch({ charge_mass_kg: Number(e.target.value) })} />
              </label>
            </div>
            <div className="field-pair">
              <label>Забойка, м
                <input type="number" step="0.01" min="0" value={current.stemming_length_m} onChange={(e) => patch({ stemming_length_m: Number(e.target.value) })} />
              </label>
              <label>Боевик, м
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={current.primer_items[0]?.position_m ?? current.primers[0] ?? 0}
                  onChange={(e) => {
                    const position = Number(e.target.value);
                    const items = current.primer_items.length
                      ? current.primer_items.map((item, index) => (index === 0 ? { ...item, position_m: position } : item))
                      : [{ position_m: position, product: "", mass_kg: 0, kind: "primer" }];
                    patch({ primer_items: items, primers: items.map((item) => item.position_m) });
                  }}
                />
              </label>
            </div>
            <label>Время заряжания
              <input type="text" placeholder="2026-08-23T12:00:00+00:00" value={current.loading_timestamp} onChange={(e) => patch({ loading_timestamp: e.target.value })} />
            </label>

            <b>Деки</b>
            {current.decks.map((deck, index) => (
              <div key={`${index}-${deck.kind}`} className="exec-deck-row">
                <select value={deck.kind} onChange={(e) => patchDeck(index, { kind: e.target.value })}>
                  {Object.entries(DECK_KIND_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
                <input type="number" step="0.01" min="0" value={deck.from_m} onChange={(e) => patchDeck(index, { from_m: Number(e.target.value) })} />
                <input type="number" step="0.01" min="0" value={deck.to_m} onChange={(e) => patchDeck(index, { to_m: Number(e.target.value) })} />
                <input type="text" placeholder="продукт" value={deck.product || deck.explosive_key} onChange={(e) => patchDeck(index, { product: e.target.value, explosive_key: e.target.value })} />
                <input type="number" step="0.1" min="0" value={deck.mass_kg} onChange={(e) => patchDeck(index, { mass_kg: Number(e.target.value) })} />
                <button type="button" className="ghost-button" onClick={() => patch({ decks: current.decks.filter((_, i) => i !== index) })}>×</button>
              </div>
            ))}
            <button type="button" className="ghost-button" onClick={() => patch({ decks: [...current.decks, emptyDeck()] })}>Добавить деку</button>

            <div className="plans-actions">
              <button type="button" className="calculate-button" onClick={recordCurrent} disabled={busy}>
                {busy ? "Пишем…" : "Записать факт"}
              </button>
              {selectedExecuted && (
                <button type="button" className="ghost-button" onClick={() => onDelete(selectedDesigned.id)}>Удалить факт</button>
              )}
            </div>
          </>
        )}

        <button type="button" className="secondary-button" onClick={onCompare} disabled={busy || asCharged.length === 0}>
          {busy ? "Считаем…" : "Сравнить с проектом"}
        </button>

        {result && (
          <>
            <div className="metrics-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
              <Metric label="Записано" value={result.as_charged_count} unit="скв." digits={0} />
              <Metric label="Сравнено" value={result.compared_count} unit="скв." digits={0} />
            </div>
            {selectedDeviation && <ChargedMetrics row={selectedDeviation} />}
            {result.warnings.length > 0 && (
              <small className="frag-warnings">{result.warnings.slice(0, 3).join(" ")}</small>
            )}
            <div className="as-drilled-table">
              <div className="as-charged-head">
                <span>Скважина</span>
                <span>Δ кг</span>
                <span>Δ забойка</span>
                <span>Продукт</span>
              </div>
              {result.deviations.map((row) => (
                <button
                  key={row.design_hole_id}
                  type="button"
                  className={`as-charged-row${warnAbs(row.charge_mass_delta_kg, 2) ? " over" : ""}${row.design_hole_id === selectedHoleId ? " active" : ""}`}
                  onClick={() => onSelectedHoleIdChange(row.design_hole_id)}
                >
                  <span>{row.design_hole_id}</span>
                  <b>{ruNumber(row.charge_mass_delta_kg, 1)}</b>
                  <b>{ruNumber(row.stemming_delta_m, 2)}</b>
                  <b>{row.product_mismatch ? "≠" : "="}</b>
                </button>
              ))}
            </div>
          </>
        )}
      </div>
    </section>
  );
}

function ChargedMetrics({ row }: { row: ChargeDeviation }) {
  return (
    <div className="metrics-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
      <Metric label={AS_CHARGED_METRIC_LABELS.charge_mass_delta_kg} value={row.charge_mass_delta_kg} unit="кг" digits={1} warn={warnAbs(row.charge_mass_delta_kg, 2)} />
      <Metric label={AS_CHARGED_METRIC_LABELS.stemming_delta_m} value={row.stemming_delta_m} unit="м" digits={2} warn={warnAbs(row.stemming_delta_m, 0.3)} />
      <Metric label={AS_CHARGED_METRIC_LABELS.primer_position_delta_m} value={row.primer_position_delta_m} unit="м" digits={2} warn={warnAbs(row.primer_position_delta_m, 0.5)} />
      <Metric label={row.depth_basis === "drilled" ? "Глубина (факт бурения)" : "Глубина (проект)"} value={row.actual_hole_depth_m} unit="м" digits={2} />
      <Metric label={AS_CHARGED_METRIC_LABELS.leftover_unloaded_m} value={row.leftover_unloaded_m} unit="м" digits={2} warn={warnAbs(row.leftover_unloaded_m, 0.4)} />
      <Metric label={AS_CHARGED_METRIC_LABELS.overcharge_m} value={row.overcharge_m} unit="м" digits={2} warn={warnAbs(row.overcharge_m, 0.1)} />
    </div>
  );
}
