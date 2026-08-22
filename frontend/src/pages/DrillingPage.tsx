import { useEffect, useMemo, useState } from "react";
import { api } from "../api/endpoints";
import { useWorkspace } from "../app/useWorkspace";
import { DataTable } from "../components/DataTable";
import type { DrillingUnitCostInput, DrillingUnitCostResult } from "../types";

const DEFAULT_INPUT: DrillingUnitCostInput = {
  volume_m: 2343.688167787891, crown_mm: 152, rig_name: "JK 830-3", tech_speed_m_h: 12,
  nonproductive_h_per_shift: 1, crown_m_per_piece: 700, crown_price_rub: 25_000,
  ppu_m_per_piece: 7_000, ppu_price_rub: 100_000, rig_tools_m_per_set: 15_000,
  rig_tools_set_price_rub: 155_000, casing_m_per_drill_m: 0.03, casing_price_rub_per_m: 450,
  shifts_toir: 2, shifts_cleaning: 1, spares_rub_per_m: 30, consumables_rub_per_m: 10,
  fot_rub_per_m: 150, object_name: "", mobilization_km: null, diesel_price_ton_rub: null,
  mobilization_rub_per_km: 450, mobilization_divisor: 6, line_release_rub_per_shift: 200,
  include_med_exams: true, overhead_production_rub: 100_000, overhead_admin_rub: 100_000, profit_factor: 1.2,
};

function num(v: number, digits = 2) {
  return v.toLocaleString("ru-RU", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function DrillingPage() {
  const { state, updateSnapshot, blastContext } = useWorkspace();
  const [result, setResult] = useState<DrillingUnitCostResult | null>(null);
  const [summaryRows, setSummaryRows] = useState<[string, string][]>([]);
  const [error, setError] = useState("");

  const workObjects = state?.references.work_object_records ?? [];
  const drillRigs = state?.references.drill_rig_records ?? [];

  const input: DrillingUnitCostInput = useMemo(
    () => ({ ...DEFAULT_INPUT, ...(state?.snapshot.drilling_calculator_input as Partial<DrillingUnitCostInput> | undefined) }),
    [state?.snapshot.drilling_calculator_input]
  );

  function set<K extends keyof DrillingUnitCostInput>(key: K, value: DrillingUnitCostInput[K]) {
    updateSnapshot({ drilling_calculator_input: { ...input, [key]: value } });
  }

  useEffect(() => {
    let cancelled = false;
    api.drillingUnit(input).then((res) => {
      if (!cancelled) { setResult(res.result); setSummaryRows(res.summary_rows); setError(""); }
    }).catch((reason) => { if (!cancelled) setError(reason instanceof Error ? reason.message : "Ошибка расчёта бурения."); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(input)]);

  const selectedObject = workObjects.find((o) => o.name === input.object_name);
  const defaultKm = selectedObject?.mobilization_km ?? 300;
  const defaultDiesel = selectedObject?.diesel_price_ton_rub ?? 80_000;

  function applyFromBlast() {
    if (!blastContext) return;
    updateSnapshot({
      drilling_calculator_input: { ...input, volume_m: blastContext.drillingFootageM || input.volume_m, crown_mm: blastContext.crownMm || input.crown_mm },
    });
  }

  function resetToDefaults() {
    updateSnapshot({ drilling_calculator_input: { ...DEFAULT_INPUT } });
  }

  return (
    <div className="page-content">
      <h2>Расчёт стоимости бурения</h2>
      <p className="page-caption">Итоговая цена за 1 п.м. подставляется в переменные расходы 1.2 на вкладке «Расчёт».</p>
      <div className="button-row">
        <button onClick={applyFromBlast} disabled={!blastContext}>Подставить объём из расчёта БВР</button>
        <button onClick={resetToDefaults}>Сбросить к Excel-смете</button>
      </div>
      {error && <div className="page-error">{error}</div>}

      <div className="drilling-grid">
        <div className="drilling-inputs">
          <h4>Исходные данные</h4>
          <label>Объект
            <select value={input.object_name} onChange={(e) => set("object_name", e.target.value)}>
              <option value="">—</option>
              {workObjects.map((o) => <option key={o.name} value={o.name}>{o.name}</option>)}
            </select>
          </label>
          <label>Объём буровых работ, п.м.<input type="number" min={1} step={10} value={input.volume_m} onChange={(e) => set("volume_m", Number(e.target.value))} /></label>
          <label>Диаметр коронки, мм<input type="number" min={100} max={250} step={1} value={input.crown_mm} onChange={(e) => set("crown_mm", Number(e.target.value))} /></label>
          <label>Тип буровой установки
            <select value={input.rig_name} onChange={(e) => set("rig_name", e.target.value)}>
              {drillRigs.map((r) => <option key={r.name} value={r.name}>{r.name}</option>)}
            </select>
          </label>
          <label>Технологическая скорость, м/ч<input type="number" min={1} step={0.5} value={input.tech_speed_m_h} onChange={(e) => set("tech_speed_m_h", Number(e.target.value))} /></label>
          <label>Непроизв. время в смену, ч<input type="number" min={0} max={10} step={0.5} value={input.nonproductive_h_per_shift} onChange={(e) => set("nonproductive_h_per_shift", Number(e.target.value))} /></label>

          <h4>Буровой инструмент</h4>
          <div className="field-pair">
            <label>Коронка, м/шт<input type="number" min={1} value={input.crown_m_per_piece} onChange={(e) => set("crown_m_per_piece", Number(e.target.value))} /></label>
            <label>Цена коронки, руб<input type="number" min={0} step={1000} value={input.crown_price_rub} onChange={(e) => set("crown_price_rub", Number(e.target.value))} /></label>
          </div>
          <div className="field-pair">
            <label>ППУ, м/шт<input type="number" min={1} value={input.ppu_m_per_piece} onChange={(e) => set("ppu_m_per_piece", Number(e.target.value))} /></label>
            <label>Цена ППУ, руб<input type="number" min={0} step={1000} value={input.ppu_price_rub} onChange={(e) => set("ppu_price_rub", Number(e.target.value))} /></label>
          </div>
          <div className="field-pair">
            <label>Оснастка, м/компл.<input type="number" min={1} value={input.rig_tools_m_per_set} onChange={(e) => set("rig_tools_m_per_set", Number(e.target.value))} /></label>
            <label>Цена комплекта, руб<input type="number" min={0} step={1000} value={input.rig_tools_set_price_rub} onChange={(e) => set("rig_tools_set_price_rub", Number(e.target.value))} /></label>
          </div>
          <div className="field-pair">
            <label>Обсадка, м/п.м.<input type="number" min={0} step={0.01} value={input.casing_m_per_drill_m} onChange={(e) => set("casing_m_per_drill_m", Number(e.target.value))} /></label>
            <label>Цена обсадки, руб/м<input type="number" min={0} step={10} value={input.casing_price_rub_per_m} onChange={(e) => set("casing_price_rub_per_m", Number(e.target.value))} /></label>
          </div>

          <h4>Смены и прочие расходы</h4>
          <div className="field-pair">
            <label>Смены на ТОиР<input type="number" min={0} value={input.shifts_toir} onChange={(e) => set("shifts_toir", Number(e.target.value))} /></label>
            <label>Смены на прочистку<input type="number" min={0} value={input.shifts_cleaning} onChange={(e) => set("shifts_cleaning", Number(e.target.value))} /></label>
          </div>
          <div className="field-pair">
            <label>Запчасти, руб/п.м.<input type="number" min={0} value={input.spares_rub_per_m} onChange={(e) => set("spares_rub_per_m", Number(e.target.value))} /></label>
            <label>Расходники, руб/п.м.<input type="number" min={0} value={input.consumables_rub_per_m} onChange={(e) => set("consumables_rub_per_m", Number(e.target.value))} /></label>
          </div>
          <div className="field-pair">
            <label>ФОТ, руб/п.м.<input type="number" min={0} value={input.fot_rub_per_m} onChange={(e) => set("fot_rub_per_m", Number(e.target.value))} /></label>
            <label>Коэфф. наценки<input type="number" min={1} max={2} step={0.05} value={input.profit_factor} onChange={(e) => set("profit_factor", Number(e.target.value))} /></label>
          </div>

          <div className="field-pair">
            <label>Мобилизация, км<input type="number" min={0} value={input.mobilization_km ?? defaultKm} onChange={(e) => set("mobilization_km", Number(e.target.value))} /></label>
            <label>Цена ДТ, руб/т<input type="number" min={0} step={1000} value={input.diesel_price_ton_rub ?? defaultDiesel} onChange={(e) => set("diesel_price_ton_rub", Number(e.target.value))} /></label>
          </div>
          <div className="field-pair">
            <label>Общепроизводственные, руб<input type="number" min={0} step={10_000} value={input.overhead_production_rub} onChange={(e) => set("overhead_production_rub", Number(e.target.value))} /></label>
            <label>Накладные, руб<input type="number" min={0} step={10_000} value={input.overhead_admin_rub} onChange={(e) => set("overhead_admin_rub", Number(e.target.value))} /></label>
          </div>
        </div>

        <div className="drilling-results">
          {result && (
            <>
              <div className="metrics-grid">
                <div><span>Себестоимость</span><strong>{num(result.cost_per_m)}</strong><small>руб/п.м.</small></div>
                <div><span>Цена (D41)</span><strong>{num(result.price_per_m)}</strong><small>руб/п.м.</small></div>
              </div>
              <h4>Сводка расчёта</h4>
              <table className="hole-metrics-table"><tbody>
                {summaryRows.map(([k, v]) => <tr key={k}><td>{k}</td><td>{v}</td></tr>)}
              </tbody></table>
              <h4>Структура цены за 1 п.м.</h4>
              <DataTable
                columns={[
                  { key: "section", label: "Раздел" },
                  { key: "name", label: "Статья" },
                  { key: "total_rub", label: "Сумма, руб", align: "right", format: (r) => (r.total_rub != null ? num(r.total_rub, 0) : "—") },
                  { key: "price_per_m", label: "руб/п.м.", align: "right", format: (r) => num(r.price_per_m) },
                  { key: "note", label: "Примечание" },
                ]}
                rows={result.lines}
              />
              <p className="cost-caption">На вкладке «Расчёт» в блоке 1.2 используется цена <b>{num(result.price_per_m)} руб/п.м.</b></p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
