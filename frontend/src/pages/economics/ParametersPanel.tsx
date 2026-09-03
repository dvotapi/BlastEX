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
  onChange,
}: {
  params: ModelParameters;
  defaults: ModelDefaults;
  onChange: (patch: Partial<ModelParameters>) => void;
}) {
  function setPercent(key: keyof ModelParameters, raw: string | null) {
    onChange({ [key]: toShare(raw) } as Partial<ModelParameters>);
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

        <div className="field-pair">
          <label>
            СЗМ
            <select
              value={params.szm_code ?? ""}
              onChange={(event) => onChange({ szm_code: event.target.value || null })}
            >
              <option value="">не выбрана</option>
              {defaults.szm.map((item) => (
                <option key={item.code} value={item.code}>{item.name}</option>
              ))}
            </select>
          </label>
          <label>
            Доставщик ВМ
            <select
              value={params.delivery_truck_code ?? ""}
              onChange={(event) => onChange({ delivery_truck_code: event.target.value || null })}
            >
              <option value="">не выбран</option>
              {defaults.delivery_trucks.map((item) => (
                <option key={item.code} value={item.code}>{item.name}</option>
              ))}
            </select>
          </label>
        </div>

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
          <input value={params.reference_revision_id || defaults.reference_revision_id} disabled />
        </label>
      </div>
    </section>
  );
}
