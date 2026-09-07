import { NumericInput } from "./NumericInput";
import type { CodeName, ServiceChargeInput, ServiceLayer } from "../../types/blockEconomics";

const LAYERS: Array<{ value: ServiceLayer; label: string }> = [
  { value: "variable", label: "переменные" },
  { value: "project_direct", label: "прямые блока" },
  { value: "production", label: "постоянные юнита" },
];

/**
 * Услуги, введённые вручную: сторонние организации, проживание и питание,
 * предрейсовый медосмотр и выпуск на линию.
 *
 * Сумма живёт в параметрах прогона — смета воспроизводима без справочника.
 * «В справочник» публикует правило затрат и убирает строку отсюда: иначе
 * услуга посчиталась бы дважды.
 */
export function ServicesPanel({
  services,
  operations,
  canEdit,
  busyCode,
  onChange,
  onMove,
}: {
  services: ServiceChargeInput[];
  operations: CodeName[];
  canEdit: boolean;
  /** Название услуги, которая сейчас переносится. */
  busyCode: string;
  onChange: (services: ServiceChargeInput[]) => void;
  onMove: (index: number) => void;
}) {
  function update(index: number, patch: Partial<ServiceChargeInput>) {
    onChange(services.map((item, i) => (i === index ? { ...item, ...patch } : item)));
  }

  function add() {
    onChange([
      ...services,
      {
        name: "",
        amount_rub: "0",
        layer: "project_direct",
        operation_code: operations.find((op) => op.code === "BLAST_EXECUTION")?.code ?? operations[0]?.code ?? "",
        per_shift: false,
      },
    ]);
  }

  return (
    <section className="panel block-economics-services">
      <header>
        <b>Услуги и прочие расходы</b>
        <span>вводятся вручную</span>
      </header>
      <div className="panel-body">
        {services.length === 0 && (
          <p className="page-caption">
            Проживание и питание, медосмотр и выпуск на линию, услуги сторонних организаций.
          </p>
        )}
        {services.map((item, index) => (
          <div className="service-row" key={index}>
            <input
              value={item.name}
              placeholder="Название услуги"
              aria-label="Название услуги"
              onChange={(event) => update(index, { name: event.target.value })}
            />
            <div className="service-row-fields">
              <label>
                Сумма, ₽{item.per_shift ? " за смену" : " на блок"}
                <NumericInput
                  value={item.amount_rub}
                  min={0}
                  step={100}
                  ariaLabel="Сумма"
                  onChange={(value) => update(index, { amount_rub: value ?? "0" })}
                />
              </label>
              <label>
                Операция
                <select
                  value={item.operation_code}
                  aria-label="Операция"
                  onChange={(event) => update(index, { operation_code: event.target.value })}
                >
                  {operations.map((op) => (
                    <option key={op.code} value={op.code}>{op.name}</option>
                  ))}
                </select>
              </label>
              <label>
                Слой
                <select
                  value={item.layer}
                  aria-label="Слой себестоимости"
                  onChange={(event) => update(index, { layer: event.target.value as ServiceLayer })}
                >
                  {LAYERS.map((layer) => (
                    <option key={layer.value} value={layer.value}>{layer.label}</option>
                  ))}
                </select>
              </label>
              <label className="service-row-check">
                <input
                  type="checkbox"
                  checked={item.per_shift}
                  onChange={(event) => update(index, { per_shift: event.target.checked })}
                />
                за смену операции
              </label>
            </div>
            <div className="service-row-actions">
              {canEdit && (
                <button
                  type="button"
                  className="row-add"
                  disabled={!item.name.trim() || Number(item.amount_rub) <= 0 || busyCode === item.name}
                  onClick={() => onMove(index)}
                  title="Опубликовать как правило затрат и убрать отсюда"
                >
                  {busyCode === item.name ? "Переносится…" : "В справочник"}
                </button>
              )}
              <button
                type="button"
                className="row-remove"
                onClick={() => onChange(services.filter((_, i) => i !== index))}
                aria-label="Убрать услугу"
              >
                ×
              </button>
            </div>
          </div>
        ))}
        <button type="button" className="row-add" onClick={add} disabled={!operations.length}>
          + Услуга
        </button>
      </div>
    </section>
  );
}
