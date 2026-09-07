import { CrewEditor } from "./CrewEditor";
import { NumericInput } from "./NumericInput";
import type { ModelDefaults, ModelParameters } from "../../types/blockEconomics";

/** Доля ↔ проценты: округление убирает двоичный хвост вида 7.000000000000001. */
const toPercent = (value: ModelParameters["overhead_rate"]) =>
  value === null || value === "" ? null : Number((Number(value) * 100).toFixed(4));

const toShare = (percent: string | null) =>
  percent === null ? null : Number((Number(percent) / 100).toFixed(6));

/** Параметры модели: всё, чего нет в техническом паспорте. */
export function ParametersPanel({
  params,
  defaults,
  computedRevisionId,
  onChange,
}: {
  params: ModelParameters;
  defaults: ModelDefaults;
  /** Ревизия, на которой посчитан текущий результат: справочники могли обновиться после загрузки. */
  computedRevisionId?: string;
  onChange: (patch: Partial<ModelParameters>) => void;
}) {
  function setPercent(key: keyof ModelParameters, raw: string | null) {
    onChange({ [key]: toShare(raw) } as Partial<ModelParameters>);
  }

  /** Пустое поле возвращает технику к нормативу справочника — ключ убирается, а не обнуляется. */
  function setPlanShifts(code: string, value: string | null) {
    const next = { ...params.machine_plan_shifts };
    if (value === null || value === "") delete next[code];
    else next[code] = value;
    onChange({ machine_plan_shifts: next });
  }

  return (
    <section className="panel block-economics-parameters">
      <header><b>Параметры модели</b><span>Экономика</span></header>
      <div className="panel-body">
        <label>
          Пакет работ
          <select value={params.package_code} onChange={(event) => onChange({ package_code: event.target.value })}>
            {defaults.packages.map((item) => (
              <option key={item.code} value={item.code}>{item.name}</option>
            ))}
          </select>
        </label>
        <label>
          Объект работ
          <input value={params.site_code} disabled />
        </label>
        <label>
          Плановый объём юнита, м³/мес
          <NumericInput
            value={params.unit_plan_volume_m3}
            min={0}
            step={1000}
            onChange={(value) => onChange({ unit_plan_volume_m3: value ?? "0" })}
          />
        </label>

        <div className="field-pair">
          <label>
            Буровой станок
            <select
              value={params.rig_code ?? ""}
              onChange={(event) => onChange({ rig_code: event.target.value || null })}
            >
              <option value="">не выбран</option>
              {defaults.rigs.map((item) => (
                <option key={item.code} value={item.code}>{item.name}</option>
              ))}
            </select>
          </label>
          <label>
            Плановые смены станка, см/мес
            <NumericInput
              value={params.rig_plan_shifts}
              allowEmpty
              min={0}
              step={1}
              placeholder="норматив станка"
              onChange={(value) => onChange({ rig_plan_shifts: value })}
            />
          </label>
        </div>

        <fieldset className="crew-fieldset machines-fieldset">
          <legend>Техника блока</legend>
          <MachineRow
            label="СЗМ"
            emptyLabel="не выбрана"
            options={defaults.szm}
            code={params.szm_code}
            planShifts={params.machine_plan_shifts}
            onCode={(value) => onChange({ szm_code: value })}
            onPlanShifts={setPlanShifts}
          />
          <MachineRow
            label="Доставщик ВМ"
            emptyLabel="не выбран"
            options={defaults.delivery_trucks}
            code={params.delivery_truck_code}
            planShifts={params.machine_plan_shifts}
            onCode={(value) => onChange({ delivery_truck_code: value })}
            onPlanShifts={setPlanShifts}
          />
          <MachineRow
            label="Тягач эмульсии"
            emptyLabel="не выбран"
            options={defaults.emulsion_trucks}
            code={params.emulsion_truck_code}
            planShifts={params.machine_plan_shifts}
            onCode={(value) => onChange({ emulsion_truck_code: value })}
            onPlanShifts={setPlanShifts}
          />
        </fieldset>

        <label>
          Исполнитель бурения
          <select
            value={params.drilling_executor}
            onChange={(event) =>
              onChange({ drilling_executor: event.target.value as ModelParameters["drilling_executor"] })
            }
          >
            <option value="OWN">свой станок</option>
            <option value="SUBCONTRACTOR">субподряд</option>
          </select>
        </label>

        <fieldset className="crew-fieldset">
          <legend>Состав бригады</legend>
          <CrewEditor
            crew={params.crew}
            positions={defaults.positions}
            onChange={(crew) => onChange({ crew })}
          />
        </fieldset>

        <div className="field-triple">
          <label>
            ОХР, %
            <NumericInput
              value={toPercent(params.overhead_rate)}
              allowEmpty
              min={0}
              max={100}
              step={0.5}
              placeholder="из справочника"
              onChange={(value) => setPercent("overhead_rate", value)}
            />
          </label>
          <label>
            Рентабельность, %
            <NumericInput
              value={toPercent(params.target_margin_rate)}
              allowEmpty
              min={0}
              max={100}
              step={0.5}
              placeholder="из справочника"
              onChange={(value) => setPercent("target_margin_rate", value)}
            />
          </label>
          <label>
            НДС, %
            <NumericInput
              value={toPercent(params.vat_rate)}
              allowEmpty
              min={0}
              max={100}
              step={1}
              placeholder="из справочника"
              onChange={(value) => setPercent("vat_rate", value)}
            />
          </label>
        </div>

        <label>
          Ревизия справочников
          <input
            value={params.reference_revision_id || computedRevisionId || defaults.reference_revision_id}
            disabled
          />
        </label>
      </div>
    </section>
  );
}

/** Машина блока: выбор типа и плановые смены, от которых зависит доля амортизации на смену. */
function MachineRow({
  label,
  emptyLabel,
  options,
  code,
  planShifts,
  onCode,
  onPlanShifts,
}: {
  label: string;
  emptyLabel: string;
  options: ModelDefaults["szm"];
  code: string | null;
  planShifts: ModelParameters["machine_plan_shifts"];
  onCode: (value: string | null) => void;
  onPlanShifts: (code: string, value: string | null) => void;
}) {
  return (
    <div className="field-pair">
      <label>
        {label}
        <select value={code ?? ""} onChange={(event) => onCode(event.target.value || null)}>
          <option value="">{emptyLabel}</option>
          {options.map((item) => (
            <option key={item.code} value={item.code}>{item.name}</option>
          ))}
        </select>
      </label>
      <label>
        Смен в месяц
        <NumericInput
          value={code ? (planShifts[code] ?? null) : null}
          allowEmpty
          min={0}
          step={1}
          placeholder="норматив техники"
          ariaLabel={`Плановые смены: ${label}`}
          onChange={(value) => code && onPlanShifts(code, value)}
        />
      </label>
    </div>
  );
}
