import { CrewEditor } from "./CrewEditor";
import type { ModelDefaults, ModelParameters } from "../../types/blockEconomics";

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
  const percent = (value: ModelParameters["overhead_rate"]) =>
    value === null || value === "" ? "" : String(Number(value) * 100);

  function setPercent(key: keyof ModelParameters, raw: string) {
    onChange({ [key]: raw === "" ? null : Number(raw) / 100 } as Partial<ModelParameters>);
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
          <input
            type="number"
            min={0}
            step={1000}
            value={String(params.unit_plan_volume_m3)}
            onChange={(event) => onChange({ unit_plan_volume_m3: event.target.value })}
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
            <input
              type="number"
              min={0}
              step={1}
              value={params.rig_plan_shifts === null ? "" : String(params.rig_plan_shifts)}
              onChange={(event) =>
                onChange({ rig_plan_shifts: event.target.value === "" ? null : event.target.value })
              }
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
            <input
              type="number" min={0} max={100} step={0.5}
              value={percent(params.overhead_rate)}
              onChange={(event) => setPercent("overhead_rate", event.target.value)}
            />
          </label>
          <label>
            Рентабельность, %
            <input
              type="number" min={0} max={100} step={0.5}
              value={percent(params.target_margin_rate)}
              onChange={(event) => setPercent("target_margin_rate", event.target.value)}
            />
          </label>
          <label>
            НДС, %
            <input
              type="number" min={0} max={100} step={1}
              value={percent(params.vat_rate)}
              onChange={(event) => setPercent("vat_rate", event.target.value)}
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
