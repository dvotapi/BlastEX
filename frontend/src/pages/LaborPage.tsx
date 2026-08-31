import { useEffect, useState } from "react";
import { api } from "../api/endpoints";
import { useWorkspace } from "../app/useWorkspace";
import { EditableTable } from "../components/EditableTable";
import type { JobPosition, LaborAssignment, LaborFOTResult } from "../types";

const DEFAULT_LABOR_CATALOG: JobPosition[] = [
  { id: "labor_master", name: "Руководитель взрывных работ (мастер БВР)", fixed_salary_monthly: 80_000, piece_rate_per_m3: 0.25 },
  { id: "labor_blasters", name: "Взрывники", fixed_salary_monthly: 55_000, piece_rate_per_m3: 0.25 },
  { id: "labor_driller", name: "Бурильщик", fixed_salary_monthly: 55_000, piece_rate_per_m3: 0.20 },
  { id: "labor_assistant", name: "Помощник бурильщика", fixed_salary_monthly: 35_000, piece_rate_per_m3: 0.15 },
  { id: "labor_miner", name: "Горнорабочий", fixed_salary_monthly: 35_000, piece_rate_per_m3: 0.15 },
  { id: "labor_driver_szm", name: "Водитель СЗМ", fixed_salary_monthly: 60_000, piece_rate_per_m3: 0.30 },
  { id: "labor_driver_del", name: "Водитель доставщика", fixed_salary_monthly: 80_000, piece_rate_per_m3: 0.30 },
];
const DEFAULT_LABOR_ASSIGNMENTS: LaborAssignment[] = [
  { id: "la_1", position_id: "labor_master", headcount: 1, volume_m3: 30_000, employee_shifts: 1 },
  { id: "la_2", position_id: "labor_blasters", headcount: 2, volume_m3: 30_000, employee_shifts: 1 },
  { id: "la_3", position_id: "labor_driver_szm", headcount: 1, volume_m3: 27_219, employee_shifts: 1 },
  { id: "la_4", position_id: "labor_driver_del", headcount: 1, volume_m3: 27_219, employee_shifts: 1 },
];

function money(n: number) { return n.toLocaleString("ru-RU", { maximumFractionDigits: 2 }); }

export function LaborPage() {
  const { state, updateSnapshot, blastContext } = useWorkspace();
  const [result, setResult] = useState<LaborFOTResult | null>(null);
  const [error, setError] = useState("");

  const catalog = state?.snapshot.labor_catalog_records ?? [];
  const assignments = state?.snapshot.labor_assignment_records ?? [];
  const shiftsPerMonth = state?.snapshot.labor_shifts_per_month ?? 5;
  const positionIds = catalog.map((p) => p.id).filter(Boolean);

  useEffect(() => {
    if (!catalog.length || !assignments.length) { setResult(null); return; }
    let cancelled = false;
    api.labor({
      labor_catalog: catalog,
      labor_assignments: assignments,
      settings: { shifts_per_month: shiftsPerMonth, net_to_gross_factor: 0.85, accident_rate: 0.0042, social_rate: 0.30, vacation_reserve_divisor: 5 },
    }).then((res) => { if (!cancelled) { setResult(res.result); setError(""); } })
      .catch((reason) => { if (!cancelled) setError(reason instanceof Error ? reason.message : "Ошибка расчёта ФОТ."); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(catalog), JSON.stringify(assignments), shiftsPerMonth]);

  function resetToDefaults() {
    updateSnapshot({
      labor_catalog_records: DEFAULT_LABOR_CATALOG,
      labor_assignment_records: DEFAULT_LABOR_ASSIGNMENTS,
      labor_shifts_per_month: 5,
    });
  }

  function applyFromBlast() {
    if (!blastContext) return;
    const next = assignments.map((row) => {
      if (["labor_master", "labor_blasters", "labor_driller", "labor_assistant"].includes(row.position_id)) {
        return { ...row, volume_m3: blastContext.blockVolumeM3 };
      }
      if (["labor_driver_szm", "labor_driver_del"].includes(row.position_id)) {
        return { ...row, volume_m3: blastContext.drillingFootageM };
      }
      return row;
    });
    updateSnapshot({ labor_assignment_records: next });
  }

  const blockVolume = blastContext?.blockVolumeM3 ?? 0;

  return (
    <div className="page-content">
      <h2>Расчёт ФОТ производственного персонала</h2>
      <p className="page-caption">Окладная часть = (оклад / смен в месяце) × смены сотрудника; сдельная = объём × расценка.</p>
      <div className="button-row">
        <button onClick={resetToDefaults}>Сбросить ФОТ к Excel-смете</button>
        <button onClick={applyFromBlast} disabled={!blastContext}>Подставить объёмы из расчёта</button>
      </div>
      {error && <div className="page-error">{error}</div>}

      <label className="field-inline">Количество рабочих смен в месяце
        <input type="number" min={1} max={31} step={1} value={shiftsPerMonth}
          onChange={(e) => updateSnapshot({ labor_shifts_per_month: Number(e.target.value) })} />
      </label>

      <h4>Справочник должностей</h4>
      <EditableTable<JobPosition>
        columns={[
          { key: "id", label: "Код", type: "text" },
          { key: "name", label: "Должность", type: "text" },
          { key: "fixed_salary_monthly", label: "Оклад, руб/мес", type: "number", step: 1000 },
          { key: "piece_rate_per_m3", label: "Сдельная, руб/м³", type: "number", step: 0.01 },
        ]}
        rows={catalog}
        onChange={(rows) => updateSnapshot({ labor_catalog_records: rows })}
        newRow={() => ({ id: "", name: "", fixed_salary_monthly: 0, piece_rate_per_m3: 0 })}
        rowKey={(r, i) => r.row_id || `labor-position-${i}`}
      />

      <h4>Штатное расписание на блок</h4>
      <EditableTable<LaborAssignment>
        columns={[
          { key: "id", label: "Код строки", type: "text" },
          { key: "position_id", label: "Должность", type: "select", options: positionIds.map((id) => ({ value: id, label: catalog.find((p) => p.id === id)?.name ?? id })) },
          { key: "headcount", label: "Ставки", type: "number", step: 0.5 },
          { key: "volume_m3", label: "Объём работ, м³", type: "number", step: 1 },
          { key: "employee_shifts", label: "Смены сотрудника", type: "number", step: 1 },
        ]}
        rows={assignments}
        onChange={(rows) => updateSnapshot({ labor_assignment_records: rows })}
        newRow={() => ({ id: `la_${Date.now()}`, position_id: positionIds[0] ?? "", headcount: 1, volume_m3: 0, employee_shifts: 1 })}
        rowKey={(r, i) => r.row_id || `labor-assignment-${i}`}
      />

      {result && (
        <div className="cost-section">
          <h4>Расчёт ФОТ</h4>
          <table className="hole-metrics-table">
            <thead><tr><th>Должность</th><th>Ставки</th><th>Объём, м³</th><th>Смены</th><th>ЗП на руки, руб</th><th>ЗП начисленная, руб</th></tr></thead>
            <tbody>
              {result.lines.map((line) => (
                <tr key={line.assignment_id}>
                  <td>{line.position_name}</td><td>{line.headcount}</td><td>{line.volume_m3.toFixed(1)}</td>
                  <td>{line.employee_shifts}</td>
                  <td>{money((line.fixed_part + line.piece_part) * line.headcount)}</td>
                  <td>{money(line.line_amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <table className="hole-metrics-table">
            <tbody>
              <tr><td>Итого заработная плата (начисленная)</td><td>{money(result.gross_salary)} руб</td></tr>
              <tr><td>Отчисления от несчастного случая</td><td>{money(result.accident_contribution)} руб</td></tr>
              <tr><td>Отчисления в фонды соц. страхования</td><td>{money(result.social_contribution)} руб</td></tr>
              <tr><td>Резерв отпусков</td><td>{money(result.vacation_reserve)} руб</td></tr>
              <tr><td>Итого отчисления</td><td>{money(result.contributions_total)} руб</td></tr>
              <tr><td><b>Итого ФОТ</b></td><td><b>{money(result.total_fot)} руб</b></td></tr>
            </tbody>
          </table>
          {blockVolume > 0 && (
            <p className="cost-caption">Удельный ФОТ: <b>{(result.total_fot / blockVolume).toFixed(2)} руб/м³</b> (объём блока {blockVolume.toLocaleString("ru-RU")} м³ с вкладки «Расчёт»)</p>
          )}
        </div>
      )}
    </div>
  );
}
