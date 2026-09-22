import type { ReactNode } from "react";
import { ruNumber } from "../../../lib/format";
import type { BlastVariant, FragmentationDetails, RockFactorBreakdown } from "../../../types";
import { ThresholdFlag } from "./ThresholdFlag";
import { formatOversize, formatQ, gridText, LEGACY_Q_MIN_KG_M3, LEGACY_THRESHOLD_TITLE, trimmed } from "./kuzramFormat";
import { BURDEN_TO_DIAMETER_WARN_ABOVE } from "./kuzramSettings";

/** Состав фактора породы A новой модели — строками для подписи в разборе. */
export function rockFactorLines(breakdown: RockFactorBreakdown | null): string[] {
  if (!breakdown) return [];
  const correction = breakdown.correction !== 1 ? ` · C(A) ${trimmed(breakdown.correction)}` : "";
  if (breakdown.method === "manual") return [`задан вручную: ${trimmed(breakdown.base)}${correction}`];
  const rdi = trimmed(breakdown.rdi ?? 0, 1);
  const hf = trimmed(breakdown.hf ?? 0, 1);
  const rmd = trimmed(breakdown.rmd ?? 0, 1);
  if (breakdown.jps !== null) {
    return [
      `0,06·(JF ${rmd} + RDI ${rdi} + HF ${hf})${correction}`,
      `JF = JCF·JPS + JPA; JPS ${trimmed(breakdown.jps)} при шаге трещин ${ruNumber(breakdown.joint_spacing_m ?? 0, 2)} м ` +
        `и приведённой сетке P = ${ruNumber(breakdown.reduced_pattern_m ?? 0, 2)} м`,
    ];
  }
  const lines = [`0,06·(RMD ${rmd} + RDI ${rdi} + HF ${hf})${correction}`];
  if (breakdown.method === "joint_factor") lines.push(`массив без трещин — RMD ${rmd}`);
  return lines;
}

/** Индекс равномерности: «сырое → принятое» (если формула дала меньше нижней границы) и L/H. */
export function uniformityText(details: FragmentationDetails): string {
  const accepted =
    Math.abs(details.uniformity_n - details.uniformity_n_raw) > 1e-9 ? ` → принято ${ruNumber(details.uniformity_n, 2)}` : "";
  const chargeToBench = details.charge_to_bench !== null ? ` (L/H ${ruNumber(details.charge_to_bench, 2)})` : "";
  return `${ruNumber(details.uniformity_n_raw, 2)}${accepted}${chargeToBench}`;
}

type Row = { label: ReactNode; now: ReactNode; old: ReactNode; key?: boolean };

/**
 * Разбор расчёта выбранной коронки: промежуточные величины обеих моделей на
 * их подобранном q. Всё приходит с сервера (`details`), окно только подписывает.
 */
export function KuzRamBreakdown({ variant, thresholdPct }: { variant: BlastVariant; thresholdPct: number }) {
  const now = variant.details;
  const old = variant.legacy.details;
  const wide = now.burden_to_diameter > BURDEN_TO_DIAMETER_WARN_ABOVE;
  const rows: Row[] = [
    { label: "Диаметр скважины d, мм", now: ruNumber(now.hole_diameter_mm, 1), old: ruNumber(old.hole_diameter_mm, 1) },
    { label: "Длина заряда L, м", now: ruNumber(now.charge_length_m, 2), old: ruNumber(old.charge_length_m, 2) },
    { label: "Масса заряда Q, кг", now: ruNumber(now.charge_mass_kg, 1), old: ruNumber(old.charge_mass_kg, 1) },
    {
      label: "Удельный расход q, кг/м³",
      now: (
        <>
          {!variant.reached && <ThresholdFlag />}
          {formatQ(now.q_kg_m3)}
        </>
      ),
      old: (
        <>
          {!variant.legacy.reached && <ThresholdFlag title={LEGACY_THRESHOLD_TITLE} />}
          {formatQ(old.q_kg_m3, ",", LEGACY_Q_MIN_KG_M3)}
        </>
      ),
      key: true,
    },
    { label: "Объём на скважину V = Q/q, м³", now: ruNumber(now.volume_per_hole_m3, 1), old: ruNumber(old.volume_per_hole_m3, 1) },
    {
      // Сетка — та же, что в сводке, таблице и на листе: сервер считает a от
      // округлённой W (`_grid`), а неокруглённое a/W · W из `details`
      // расходится с ней на сотую.
      label: "ЛНС W · сетка a × b, м",
      now: `${ruNumber(now.burden_m, 2)} · ${gridText(variant.grid_a_m, variant.grid_b_m)}`,
      old: `${ruNumber(old.burden_m, 2)} · ${gridText(variant.legacy.grid_a_m, variant.legacy.grid_b_m)}`,
    },
    {
      label: "W/d — ЛНС к диаметру скважины",
      now: (
        <>
          {ruNumber(now.burden_to_diameter, 1)}
          {wide && <span className="kuzram-warning-mark">выше {BURDEN_TO_DIAMETER_WARN_ABOVE}</span>}
        </>
      ),
      old: ruNumber(old.burden_to_diameter, 1),
    },
    {
      label: (
        <>
          Фактор породы A
          {rockFactorLines(now.rock_factor).map((line) => (
            <small key={line}>Kuz-Ram: {line}</small>
          ))}
          <small>до исправления: 0,12·(UCS/20 + 2,5ρ + 7)</small>
        </>
      ),
      now: ruNumber(now.rock_factor_a, 2),
      old: ruNumber(old.rock_factor_a, 2),
    },
    {
      label: "Сила ВВ RE (к тротилу) · показатель",
      now: `${ruNumber(now.re_weight, 3)} · ${now.strength_exponent}`,
      old: `${ruNumber(old.re_weight, 3)} · ${old.strength_exponent}`,
    },
    { label: "Средний кусок x50, мм", now: ruNumber(now.x50_mm, 1), old: ruNumber(old.x50_mm, 1) },
    { label: "Индекс равномерности n", now: uniformityText(now), old: uniformityText(old) },
    { label: "Характерный размер xc, мм", now: ruNumber(now.characteristic_size_mm, 1), old: ruNumber(old.characteristic_size_mm, 1) },
    {
      label: "Негабарит, %",
      now: formatOversize(now.oversize_pct, variant.reached, thresholdPct),
      old: formatOversize(old.oversize_pct, variant.legacy.reached, thresholdPct),
      key: true,
    },
  ];

  return (
    <section className="kuzram-card" aria-labelledby="kuzram-breakdown-title">
      <h3 id="kuzram-breakdown-title">Разбор расчёта</h3>
      <div className="kuzram-table-scroll">
        <table className="kuzram-table kuzram-breakdown">
          <caption>Коронка {trimmed(variant.crown_mm)} мм — каждая модель на своём подобранном q.</caption>
          <thead>
            <tr>
              <th scope="col">Величина</th>
              <th scope="col" className="sep">Kuz-Ram</th>
              <th scope="col" className="sep">До исправления</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index} className={row.key ? "key" : undefined}>
                <th scope="row">{row.label}</th>
                <td className="sep">{row.now}</td>
                <td className="sep">{row.old}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {wide && (
        <p className="kuzram-warning">
          W/d = {ruNumber(now.burden_to_diameter, 1)} — выше {BURDEN_TO_DIAMETER_WARN_ABOVE}: сетка редкая для этого диаметра,
          Каннингем рекомендует 25–35. Прогноз модели здесь менее надёжен; подбор q это не ограничивает.
        </p>
      )}
    </section>
  );
}
