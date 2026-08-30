import type {
  EconomicServiceLine,
  EconomicsReferenceItem,
  MonthlyEconomicPlan,
  Numeric,
  OperationExecutor,
  OperationOverride,
  SiteConditions,
} from "../../types/economics";

const EXECUTORS: Array<{ value: OperationExecutor; label: string }> = [
  { value: "OWN", label: "Собственные силы" },
  { value: "CUSTOMER", label: "Заказчик" },
  { value: "SUBCONTRACTOR", label: "Субподрядчик" },
  { value: "THIRD_PARTY_SUPPLIER", label: "Сторонний поставщик" },
  { value: "OUT_OF_SCOPE", label: "Не входит" },
];

const PHYSICAL_FIELDS: Array<{ key: string; label: string; step?: number }> = [
  { key: "rock_volume_m3", label: "Горная масса, м³" },
  { key: "drilling_m", label: "Бурение, м" },
  { key: "contour_drilling_m", label: "Контур, м" },
  { key: "explosive_kg", label: "ВМ, кг" },
  { key: "holes", label: "Скважины, шт." },
  { key: "blasts", label: "Взрывы, шт." },
  { key: "base_drilling_productivity_m_h", label: "Производительность, м/ч", step: 0.1 },
  { key: "base_contour_productivity_m_h", label: "Контурная производит., м/ч", step: 0.1 },
  { key: "szm_hours", label: "СЗМ, ч", step: 0.1 },
  { key: "excavator_hours", label: "Экскаватор, ч", step: 0.1 },
  { key: "distance_km", label: "Расстояние, км", step: 0.1 },
  { key: "trips", label: "Рейсы, шт." },
  { key: "person_days", label: "Человеко-дни", step: 0.1 },
  { key: "person_nights", label: "Человеко-ночи", step: 0.1 },
  { key: "mobilizations", label: "Мобилизации" },
  { key: "demobilizations", label: "Демобилизации" },
];

function currentMonth(): string {
  const date = new Date();
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
}

function uid(prefix: string): string {
  const token = typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${token}`;
}

function defaultConditions(): SiteConditions {
  return {
    bench_surface_condition_code: "PREPARED",
    uncleared_rock_share_pct: 0,
    drilling_productivity_factor: 1,
    stakeout_mode: "CUSTOMER_ALL_HOLES",
    refueling_available: true,
    customer_provides_fuel: false,
    maintenance_box_available: true,
    canteen_available: true,
    accommodation_available: true,
    meal_cost_rub_person_day: 0,
    accommodation_cost_rub_person_night: 0,
    own_fuel_delivery_cost_rub_trip: 0,
    mobile_maintenance_cost_rub_shift: 0,
    infrastructure_comment: "",
  };
}

export function newServiceLine(packageCode: string): EconomicServiceLine {
  return {
    id: uid("line"),
    name: "Новая строка работ",
    package_code: packageCode,
    customer_code: "",
    site_code: "",
    billing_unit: "M3",
    market_price_rub: 0,
    monthly_plans: [{ month: currentMonth(), billed_quantity: 0, physical: {} }],
    operation_overrides: [],
    site_conditions: defaultConditions(),
    options: { internal_transfer: true },
    replaces_service_line_id: null,
  };
}

function numeric(value: string): number | null {
  return value === "" ? null : Number(value);
}

function packageOperations(item: EconomicsReferenceItem | undefined): Array<{ operation_code: string; optional: boolean }> {
  const raw = item?.payload.operations;
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((value) => {
    if (typeof value === "string") return [{ operation_code: value, optional: false }];
    if (!value || typeof value !== "object") return [];
    const row = value as Record<string, unknown>;
    return [{ operation_code: String(row.operation_code ?? ""), optional: Boolean(row.optional) }];
  }).filter((row) => row.operation_code);
}

function overrideFor(line: EconomicServiceLine, code: string): OperationOverride | undefined {
  return line.operation_overrides.find((item) => item.operation_code === code);
}

function defaultExecutor(line: EconomicServiceLine, code: string): OperationExecutor {
  if (code === "DRILL_DESIGN" && !Boolean(line.options.own_drill_design)) return "CUSTOMER";
  if (code === "SURVEY_STAKEOUT" && line.site_conditions.stakeout_mode === "CUSTOMER_ALL_HOLES") return "CUSTOMER";
  return "OWN";
}

function defaultOptionalEnabled(line: EconomicServiceLine, code: string, optional: boolean): boolean {
  if (!optional) return true;
  if (code === "CHARGING_HOSE_ASSISTANCE") return Boolean(line.options.charging_hose_assistance);
  if (code === "OVERSIZE_BREAKING") return Boolean(line.options.secondary_breaking);
  if (code === "VM_DELIVERY_SITE") return Boolean(line.options.delivery_included);
  if (code === "DRILL_DESIGN") return Boolean(line.options.own_drill_design);
  if (code === "COMPONENT_MANUFACTURE") return line.options.component_supply_mode === "OWN_COMPONENT_PRODUCTION";
  if (code === "COMPONENT_PURCHASE") return line.options.component_supply_mode === "PURCHASED_COMPONENTS";
  return false;
}

export function ServiceLinesEditor({
  title,
  caption,
  lines,
  onChange,
  packages,
  operations,
  surfaceConditions,
  replacementLines = [],
}: {
  title: string;
  caption: string;
  lines: EconomicServiceLine[];
  onChange: (lines: EconomicServiceLine[]) => void;
  packages: EconomicsReferenceItem[];
  operations: EconomicsReferenceItem[];
  surfaceConditions: EconomicsReferenceItem[];
  replacementLines?: EconomicServiceLine[];
}) {
  const operationNames = new Map(operations.map((item) => [item.code, item.name]));

  function updateLine(index: number, patch: Partial<EconomicServiceLine>) {
    onChange(lines.map((line, i) => i === index ? { ...line, ...patch } : line));
  }

  function updateCondition(index: number, patch: Partial<SiteConditions>) {
    updateLine(index, { site_conditions: { ...lines[index].site_conditions, ...patch } });
  }

  function updateOption(index: number, key: string, value: unknown) {
    updateLine(index, { options: { ...lines[index].options, [key]: value } });
  }

  function updatePlan(lineIndex: number, planIndex: number, patch: Partial<MonthlyEconomicPlan>) {
    updateLine(lineIndex, {
      monthly_plans: lines[lineIndex].monthly_plans.map((plan, i) => i === planIndex ? { ...plan, ...patch } : plan),
    });
  }

  function updatePhysical(lineIndex: number, planIndex: number, key: string, value: Numeric | null) {
    const plan = lines[lineIndex].monthly_plans[planIndex];
    const physical = { ...plan.physical };
    if (value === null) delete physical[key];
    else physical[key] = value;
    updatePlan(lineIndex, planIndex, { physical });
  }

  function updateOperation(
    lineIndex: number,
    operationCode: string,
    patch: Partial<OperationOverride>,
    defaults: Pick<OperationOverride, "executor" | "enabled">
  ) {
    const line = lines[lineIndex];
    const current = overrideFor(line, operationCode) ?? {
      operation_code: operationCode,
      executor: defaults.executor,
      enabled: defaults.enabled,
      quantity: null,
      subcontract_rate_rub: null,
      supervision_cost_rub: 0,
    };
    const next = { ...current, ...patch };
    updateLine(lineIndex, {
      operation_overrides: [
        ...line.operation_overrides.filter((item) => item.operation_code !== operationCode),
        next,
      ],
    });
  }

  return (
    <section className="economic-lines-section">
      <div className="economic-section-heading">
        <div><h3>{title}</h3><p>{caption}</p></div>
        <button className="secondary-button" onClick={() => onChange([...lines, newServiceLine(packages[0]?.code ?? "DRILL_AND_BLAST")])}>+ Строка работ</button>
      </div>
      {lines.length === 0 && <div className="economic-empty">Строки работ не добавлены.</div>}
      {lines.map((line, lineIndex) => {
        const packageItem = packages.find((item) => item.code === line.package_code);
        const packageOps = packageOperations(packageItem);
        return (
          <article className="economic-line-card" key={line.id}>
            <header>
              <b>{line.name || "Строка работ"}</b>
              <button className="row-remove" onClick={() => onChange(lines.filter((_, i) => i !== lineIndex))}>Удалить строку</button>
            </header>
            <div className="economic-fields-grid">
              <label>Наименование<input value={line.name} onChange={(e) => updateLine(lineIndex, { name: e.target.value })} /></label>
              <label>Пакет работ<select value={line.package_code} onChange={(e) => updateLine(lineIndex, { package_code: e.target.value, operation_overrides: [] })}>{packages.map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}</select></label>
              <label>Заказчик, код<input value={line.customer_code} onChange={(e) => updateLine(lineIndex, { customer_code: e.target.value.toUpperCase() })} /></label>
              <label>Карьер, код<input value={line.site_code} onChange={(e) => updateLine(lineIndex, { site_code: e.target.value.toUpperCase() })} /></label>
              <label>Единица оплаты<select value={line.billing_unit} onChange={(e) => updateLine(lineIndex, { billing_unit: e.target.value })}><option value="M3">м³</option><option value="M">м</option><option value="M2">м²</option><option value="KG">кг</option><option value="T">т</option><option value="HOUR">машино-час</option><option value="TRIP">рейс</option><option value="CONTRACT_LINE">договорная позиция</option></select></label>
              <label>Рыночная цена, ₽<input type="number" min="0" value={line.market_price_rub} onChange={(e) => updateLine(lineIndex, { market_price_rub: Number(e.target.value) })} /></label>
              {replacementLines.length > 0 && <label>Заменяет строку базы<select value={line.replaces_service_line_id ?? ""} onChange={(e) => updateLine(lineIndex, { replaces_service_line_id: e.target.value || null })}><option value="">Добавить как новую</option>{replacementLines.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}
            </div>

            <details className="economic-details" open>
              <summary>Помесячный производственный план</summary>
              <div className="table-scroll economic-plan-table">
                <table>
                  <thead><tr><th>Месяц</th><th>Оплачиваемый объём</th>{PHYSICAL_FIELDS.map((field) => <th key={field.key}>{field.label}</th>)}<th /></tr></thead>
                  <tbody>
                    {line.monthly_plans.map((plan, planIndex) => (
                      <tr key={`${line.id}-${plan.month}-${planIndex}`}>
                        <td><input type="month" value={plan.month} onChange={(e) => updatePlan(lineIndex, planIndex, { month: e.target.value })} /></td>
                        <td><input type="number" min="0" value={plan.billed_quantity} onChange={(e) => updatePlan(lineIndex, planIndex, { billed_quantity: Number(e.target.value) })} /></td>
                        {PHYSICAL_FIELDS.map((field) => (
                          <td key={field.key}><input type="number" min="0" step={field.step ?? 1} value={plan.physical[field.key] ?? ""} onChange={(e) => updatePhysical(lineIndex, planIndex, field.key, numeric(e.target.value))} /></td>
                        ))}
                        <td><button className="row-remove" onClick={() => updateLine(lineIndex, { monthly_plans: line.monthly_plans.filter((_, i) => i !== planIndex) })}>✕</button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <button className="row-add" onClick={() => updateLine(lineIndex, { monthly_plans: [...line.monthly_plans, { month: currentMonth(), billed_quantity: 0, physical: {} }] })}>+ Месяц</button>
            </details>

            <details className="economic-details">
              <summary>Границы работ и исполнители</summary>
              <div className="economic-options-grid">
                <label>Компоненты ЭВВ<select value={String(line.options.component_supply_mode ?? "")} onChange={(e) => updateOption(lineIndex, "component_supply_mode", e.target.value)}><option value="">Не задано</option><option value="OWN_COMPONENT_PRODUCTION">Свой пункт изготовления</option><option value="PURCHASED_COMPONENTS">Закупаем компоненты</option></select></label>
                <label className="check-field"><input type="checkbox" checked={Boolean(line.options.own_drill_design)} onChange={(e) => updateOption(lineIndex, "own_drill_design", e.target.checked)} />Проект бурения выполняем мы</label>
                <label className="check-field"><input type="checkbox" checked={Boolean(line.options.charging_hose_assistance)} onChange={(e) => updateOption(lineIndex, "charging_hose_assistance", e.target.checked)} />Горнорабочий с зарядным рукавом</label>
                <label className="check-field"><input type="checkbox" checked={Boolean(line.options.secondary_breaking)} onChange={(e) => updateOption(lineIndex, "secondary_breaking", e.target.checked)} />Вторичное дробление</label>
                <label className="check-field"><input type="checkbox" checked={Boolean(line.options.delivery_included)} onChange={(e) => updateOption(lineIndex, "delivery_included", e.target.checked)} />Доставка входит в продажу</label>
                {line.package_code === "VM_WAREHOUSE_TRANSFER" && <label className="check-field"><input type="checkbox" checked={Boolean(line.options.internal_transfer ?? true)} onChange={(e) => updateOption(lineIndex, "internal_transfer", e.target.checked)} />Внутреннее перемещение без выручки</label>}
              </div>
              <div className="table-scroll operation-scope-table">
                <table>
                  <thead><tr><th>Включена</th><th>Операция</th><th>Исполнитель</th><th>Ставка внешнего исполнителя, ₽/ед.</th><th>Собственный контроль, ₽</th></tr></thead>
                  <tbody>
                    {packageOps.map((entry) => {
                      const override = overrideFor(line, entry.operation_code);
                      const enabled = override?.enabled ?? defaultOptionalEnabled(line, entry.operation_code, entry.optional);
                      const executor = override?.executor ?? defaultExecutor(line, entry.operation_code);
                      return (
                        <tr key={entry.operation_code}>
                          <td><input type="checkbox" checked={enabled} onChange={(e) => updateOperation(lineIndex, entry.operation_code, { enabled: e.target.checked }, { enabled, executor })} /></td>
                          <td>{operationNames.get(entry.operation_code) ?? entry.operation_code}{entry.optional && <small> опция</small>}</td>
                          <td><select value={executor} onChange={(e) => updateOperation(lineIndex, entry.operation_code, { executor: e.target.value as OperationExecutor }, { enabled, executor })}>{EXECUTORS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></td>
                          <td><input type="number" min="0" value={override?.subcontract_rate_rub ?? ""} disabled={executor !== "SUBCONTRACTOR" && executor !== "THIRD_PARTY_SUPPLIER"} onChange={(e) => updateOperation(lineIndex, entry.operation_code, { subcontract_rate_rub: numeric(e.target.value) }, { enabled, executor })} /></td>
                          <td><input type="number" min="0" value={override?.supervision_cost_rub ?? 0} disabled={executor !== "SUBCONTRACTOR" && executor !== "THIRD_PARTY_SUPPLIER"} onChange={(e) => updateOperation(lineIndex, entry.operation_code, { supervision_cost_rub: Number(e.target.value) }, { enabled, executor })} /></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </details>

            <details className="economic-details">
              <summary>Условия бурения и инфраструктура объекта</summary>
              <div className="economic-fields-grid">
                <label>Качество поверхности<select value={line.site_conditions.bench_surface_condition_code} onChange={(e) => updateCondition(lineIndex, { bench_surface_condition_code: e.target.value })}>{surfaceConditions.map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}</select></label>
                <label>Невыбранная масса, %<input type="number" min="0" max="100" value={line.site_conditions.uncleared_rock_share_pct} onChange={(e) => updateCondition(lineIndex, { uncleared_rock_share_pct: Number(e.target.value) })} /></label>
                <label>Коэффициент производительности<input type="number" min="0.01" step="0.01" value={line.site_conditions.drilling_productivity_factor} onChange={(e) => updateCondition(lineIndex, { drilling_productivity_factor: Number(e.target.value) })} /></label>
                <label>Вынос скважин<select value={line.site_conditions.stakeout_mode} onChange={(e) => updateCondition(lineIndex, { stakeout_mode: e.target.value as SiteConditions["stakeout_mode"] })}><option value="CUSTOMER_CONTROL_POINTS">Заказчик — опорные</option><option value="CUSTOMER_ALL_HOLES">Заказчик — все</option><option value="CONTRACTOR_ALL_HOLES">Подрядчик — все</option></select></label>
                <label className="check-field"><input type="checkbox" checked={line.site_conditions.refueling_available} onChange={(e) => updateCondition(lineIndex, { refueling_available: e.target.checked })} />Заправка доступна</label>
                <label className="check-field"><input type="checkbox" checked={line.site_conditions.customer_provides_fuel} onChange={(e) => updateCondition(lineIndex, { customer_provides_fuel: e.target.checked })} />Топливо заказчика</label>
                <label className="check-field"><input type="checkbox" checked={line.site_conditions.maintenance_box_available} onChange={(e) => updateCondition(lineIndex, { maintenance_box_available: e.target.checked })} />Бокс ТОиР доступен</label>
                <label className="check-field"><input type="checkbox" checked={line.site_conditions.canteen_available} onChange={(e) => updateCondition(lineIndex, { canteen_available: e.target.checked })} />Столовая доступна</label>
                <label className="check-field"><input type="checkbox" checked={line.site_conditions.accommodation_available} onChange={(e) => updateCondition(lineIndex, { accommodation_available: e.target.checked })} />Проживание доступно</label>
                <label>Питание, ₽/чел.-день<input type="number" min="0" value={line.site_conditions.meal_cost_rub_person_day} onChange={(e) => updateCondition(lineIndex, { meal_cost_rub_person_day: Number(e.target.value) })} /></label>
                <label>Проживание, ₽/ночь<input type="number" min="0" value={line.site_conditions.accommodation_cost_rub_person_night} onChange={(e) => updateCondition(lineIndex, { accommodation_cost_rub_person_night: Number(e.target.value) })} /></label>
                <label>Своя доставка топлива, ₽/рейс<input type="number" min="0" value={line.site_conditions.own_fuel_delivery_cost_rub_trip} onChange={(e) => updateCondition(lineIndex, { own_fuel_delivery_cost_rub_trip: Number(e.target.value) })} /></label>
                <label>Мобильное ТОиР, ₽/смена<input type="number" min="0" value={line.site_conditions.mobile_maintenance_cost_rub_shift} onChange={(e) => updateCondition(lineIndex, { mobile_maintenance_cost_rub_shift: Number(e.target.value) })} /></label>
              </div>
            </details>
          </article>
        );
      })}
    </section>
  );
}
