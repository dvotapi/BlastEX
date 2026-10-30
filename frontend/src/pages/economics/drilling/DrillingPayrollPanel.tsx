/**
 * Зарплата экипажа бурения на странице «Бурение»: источник ФОТ (ставки или
 * методика), условия, по которым посчитан плановый темп, и разбивка по
 * методике. Это те же параметры черновика (`payroll_source`), что видит смета:
 * переключатель здесь меняет блок, а не отдельный расчёт.
 */
import { useId } from "react";
import { amount, money } from "../format";
import { PayrollBreakdown } from "../PayrollBreakdown";
import type { BlockEconomics, ModelParameters } from "../../../types/blockEconomics";

export type DrillingPayrollPanelProps = {
  params: ModelParameters;
  /** null — расчёт ещё не пришёл. */
  economics: BlockEconomics | null;
  canEdit: boolean;
  onChange: (patch: Partial<ModelParameters>) => void;
};

const METHOD_NOT_APPLIED = ["Методика ФОТ не применена", "ФОТ экипажа бурения посчитан по ставкам"];

export function DrillingPayrollPanel({ params, economics, canEdit, onChange }: DrillingPayrollPanelProps) {
  const sourceName = `payroll_source-${useId()}`;
  const subcontracted = params.drilling_executor === "SUBCONTRACTOR";
  const payroll = economics?.payroll ?? null;
  const methodology = params.payroll_source === "PAYROLL";
  // Причина видна, только если её несёт текущий ответ: сразу после
  // переключения ответ ещё посчитан по ставкам и текста про методику нет.
  const reason =
    economics?.warnings.find((text) => METHOD_NOT_APPLIED.some((prefix) => text.startsWith(prefix))) ?? "";
  const values = economics?.natural.values ?? {};
  const conditionName = payroll?.pace.condition_name || undefined;

  return (
    <section className="panel drilling-payroll" aria-label="Зарплата экипажа бурения">
      <h3>Зарплата экипажа бурения</h3>
      <fieldset
        className={subcontracted ? "labor-source labor-source-inactive" : "labor-source"}
        disabled={!canEdit || subcontracted}
      >
        <legend>Источник ФОТ экипажа</legend>
        <label>
          <input
            type="radio"
            name={sourceName}
            value="RATES"
            checked={params.payroll_source === "RATES"}
            onChange={() => onChange({ payroll_source: "RATES" })}
          />
          Ставки
        </label>
        <label>
          <input
            type="radio"
            name={sourceName}
            value="PAYROLL"
            checked={methodology}
            onChange={() => onChange({ payroll_source: "PAYROLL" })}
          />
          Методика ФОТ
        </label>
        {subcontracted && (
          <p className="labor-source-note">
            Бурение на субподряде: ФОТ экипажа считает подрядчик. Сохранённый выбор не применяется
          </p>
        )}
      </fieldset>

      {methodology && !subcontracted && payroll === null && reason && (
        <p className="labor-source-note">{reason}</p>
      )}

      {methodology && !subcontracted && (
        <dl className="drilling-payroll-facts">
          <div>
            <dt>Технологическая скорость</dt>
            <dd>
              {values.drilling_tech_speed_m_per_h === undefined
                ? "—"
                : `${amount(Number(values.drilling_tech_speed_m_per_h), 1)} м/ч`}
            </dd>
          </div>
          <div>
            <dt>Коммерческая скорость</dt>
            <dd>
              {values.v_commercial_m_per_shift === undefined
                ? "—"
                : `${amount(Number(values.v_commercial_m_per_shift))} м/смену`}
            </dd>
          </div>
          <div>
            <dt>Откуда скорость</dt>
            <dd>{conditionName ?? "—"}</dd>
          </div>
        </dl>
      )}
      {methodology && !subcontracted && (
        <p className="drilling-payroll-hint">
          Скорость и простой берутся из справочника «Условия бурения» (станок, объект, порода) и здесь не правятся.
        </p>
      )}

      {payroll ? (
        <PayrollBreakdown payroll={payroll} />
      ) : (
        methodology && !subcontracted && !reason && <p className="labor-source-note">Расчёт выполняется…</p>
      )}

      {payroll === null && !methodology && economics && (
        <p className="drilling-payroll-hint">
          ФОТ экипажа считается по ставкам должностей. Для расчёта по методике выберите «Методика ФОТ».
        </p>
      )}
      {economics?.natural.values.drilling_rub_per_m !== undefined && (
        <p className="drilling-payroll-hint">
          Стоимость 1 п.м. бурения в смете: {money(Number(economics.natural.values.drilling_rub_per_m))} ₽/м.
        </p>
      )}
    </section>
  );
}
