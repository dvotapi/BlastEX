import type { Explosive } from "../../types";
import type {
  BlastDomain,
  ChargeAction,
  ChargeRules,
  ChargeTemplate,
  DeckKind,
  DeckingType,
} from "../../types/design";
import {
  CHARGE_REGION_LABELS,
  DECK_KIND_LABELS,
  GEOLOGICAL_INTERVAL_LABELS,
  HOLE_KIND_LABELS,
  emptyChargeAction,
  emptyChargeTemplate,
  exampleChargeTemplates,
} from "../../types/design";
import { RoleBadge } from "./RoleBadge";

const WATER_OPTIONS = [
  { value: "", label: "любая" },
  { value: "dry", label: "сухо" },
  { value: "moist", label: "влажно" },
  { value: "wet", label: "обводнено" },
  { value: "flowing", label: "приток" },
];

const ACTION_KINDS: DeckKind[] = [
  "bulk_explosive",
  "packaged_explosive",
  "stemming",
  "air_deck",
  "inert_deck",
  "water_deck",
  "primer",
  "booster",
  "detonator",
];

function optionalNumber(raw: string): number | null {
  if (raw.trim() === "") return null;
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
}

export function ChargePanel({
  rules,
  explosives,
  explosiveKey,
  domains,
  onExplosiveKeyChange,
  onChange,
  onCalculate,
  busy,
}: {
  rules: ChargeRules;
  explosives: Explosive[];
  explosiveKey: string;
  domains: BlastDomain[];
  onExplosiveKeyChange: (key: string) => void;
  onChange: (patch: Partial<ChargeRules>) => void;
  onCalculate: () => void;
  busy: boolean;
}) {
  function num(key: keyof ChargeRules) {
    return {
      value: (rules[key] as number) ?? 0,
      onChange: (e: React.ChangeEvent<HTMLInputElement>) => onChange({ [key]: Number(e.target.value) } as Partial<ChargeRules>),
    };
  }

  const stemmingFixed = rules.stemming_m !== null;
  const templates = rules.templates ?? [];

  function patchTemplate(id: string, patch: Partial<ChargeTemplate>) {
    onChange({
      templates: templates.map((item) => (item.id === id ? { ...item, ...patch } : item)),
    });
  }

  function patchCondition(id: string, patch: Partial<ChargeTemplate["conditions"]>) {
    const current = templates.find((item) => item.id === id);
    if (!current) return;
    patchTemplate(id, { conditions: { ...current.conditions, ...patch } });
  }

  function patchAction(id: string, index: number, patch: Partial<ChargeAction>) {
    const current = templates.find((item) => item.id === id);
    if (!current) return;
    patchTemplate(id, {
      actions: current.actions.map((action, i) => (i === index ? { ...action, ...patch } : action)),
    });
  }

  return (
    <section className="panel">
      <header><b>Заряжание</b><RoleBadge role="designed" /></header>
      <div className="panel-body">
        <label>Взрывчатое вещество по умолчанию
          <select value={explosiveKey} onChange={(e) => onExplosiveKeyChange(e.target.value)}>
            {explosives.map((item) => <option key={item.key} value={item.key}>{item.name}</option>)}
          </select>
        </label>

        <label>Коэффициент разбуривания<input type="number" min="1" max="1.5" step="0.01" {...num("hole_oversize_coeff")} /></label>

        <div className="pattern-type-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
          <button
            type="button"
            className={`pattern-type-option${stemmingFixed ? " active" : ""}`}
            onClick={() => onChange({ stemming_m: rules.stemming_m ?? 3 })}
          >
            <b>Забойка, м</b><small>фиксированная длина</small>
          </button>
          <button
            type="button"
            className={`pattern-type-option${!stemmingFixed ? " active" : ""}`}
            onClick={() => onChange({ stemming_m: null })}
          >
            <b>Забойка, k×d</b><small>по диаметру скважины</small>
          </button>
        </div>
        {stemmingFixed ? (
          <label>Длина забойки, м
            <input type="number" min="0" step="0.1" value={rules.stemming_m ?? 0} onChange={(e) => onChange({ stemming_m: Number(e.target.value) })} />
          </label>
        ) : (
          <label>Забойка, диаметров скважины<input type="number" min="1" step="1" {...num("stemming_k")} /></label>
        )}

        <label>Длина «дна», м<input type="number" min="0" step="0.1" {...num("bottom_length_m")} /></label>

        <div className="pattern-type-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
          {(["continuous", "spaced"] as DeckingType[]).map((value) => (
            <button
              key={value}
              type="button"
              className={`pattern-type-option${rules.decking === value ? " active" : ""}`}
              onClick={() => onChange({ decking: value })}
            >
              <b>{value === "continuous" ? "Сплошной заряд" : "Рассредоточенный"}</b>
              <small>{value === "continuous" ? "одна колонна" : "деки + промежутки"}</small>
            </button>
          ))}
        </div>

        {rules.decking === "spaced" && (
          <div className="field-pair">
            <label>Число зарядов<input type="number" min="2" step="1" {...num("deck_count")} /></label>
            <label>Воздушный промежуток, м<input type="number" min="0" step="0.1" {...num("air_gap_m")} /></label>
          </div>
        )}

        <label>Отступ боевика от торца деки, м<input type="number" min="0" step="0.05" {...num("primer_offset_m")} /></label>

        <div className="field-pair">
          <label>Сетка a, м (для q)<input type="number" min="0" step="0.1" {...num("grid_a_m")} /></label>
          <label>Сетка b, м (для q)<input type="number" min="0" step="0.1" {...num("grid_b_m")} /></label>
        </div>

        <div className="template-head">
          <b>Шаблоны заряжания</b>
          <small>условия → действия, по приоритету</small>
        </div>
        <small>
          Если шаблонов нет, действует простая схема выше. Шаблоны читают тип скважины,
          ряд, геологию, воду и ЛНС и могут класть в одну скважину несколько ВВ.
        </small>

        <div className="geology-list">
          {templates.length === 0 && (
            <div className="surface-card empty"><b>Шаблонов нет</b><small>простые правила или пример дно/сухо/мокро</small></div>
          )}
          {templates.map((template) => (
            <TemplateCard
              key={template.id}
              template={template}
              explosives={explosives}
              domains={domains}
              onPatch={(patch) => patchTemplate(template.id, patch)}
              onPatchCondition={(patch) => patchCondition(template.id, patch)}
              onPatchAction={(index, patch) => patchAction(template.id, index, patch)}
              onAddAction={() => patchTemplate(template.id, { actions: [...template.actions, emptyChargeAction()] })}
              onRemoveAction={(index) => patchTemplate(template.id, { actions: template.actions.filter((_, i) => i !== index) })}
              onDelete={() => onChange({ templates: templates.filter((item) => item.id !== template.id) })}
            />
          ))}
        </div>

        <div className="plans-actions">
          <button type="button" className="secondary-button" onClick={() => onChange({ templates: [...templates, emptyChargeTemplate(templates)] })}>
            Добавить шаблон
          </button>
          <button type="button" className="secondary-button" onClick={() => onChange({ templates: exampleChargeTemplates(), bottom_length_m: 2 })}>
            Пример: дно / сухо / мокро
          </button>
        </div>

        <button className="calculate-button" onClick={onCalculate} disabled={busy}>
          {busy ? "Считаем заряжание…" : "Рассчитать заряжание"}
        </button>
        <small>Масса заряда считается тем же методом, что и смета — совпадает с ней до килограмма.</small>
      </div>
    </section>
  );
}

function TemplateCard({
  template,
  explosives,
  domains,
  onPatch,
  onPatchCondition,
  onPatchAction,
  onAddAction,
  onRemoveAction,
  onDelete,
}: {
  template: ChargeTemplate;
  explosives: Explosive[];
  domains: BlastDomain[];
  onPatch: (patch: Partial<ChargeTemplate>) => void;
  onPatchCondition: (patch: Partial<ChargeTemplate["conditions"]>) => void;
  onPatchAction: (index: number, patch: Partial<ChargeAction>) => void;
  onAddAction: () => void;
  onRemoveAction: (index: number) => void;
  onDelete: () => void;
}) {
  const cond = template.conditions;
  return (
    <div className={`template-card${template.enabled ? "" : " disabled"}`}>
      <div className="template-card-head">
        <label className="checkbox-row">
          <input type="checkbox" checked={template.enabled} onChange={(e) => onPatch({ enabled: e.target.checked })} />
          вкл.
        </label>
        <input
          type="text"
          value={template.name}
          onChange={(e) => onPatch({ name: e.target.value })}
          aria-label="Название шаблона"
        />
        <label className="template-priority">
          приоритет
          <input type="number" step="1" value={template.priority} onChange={(e) => onPatch({ priority: Number(e.target.value) })} />
        </label>
        <button type="button" className="plans-list-delete" onClick={onDelete} title="Удалить шаблон">×</button>
      </div>

      <details>
        <summary>Условия</summary>
        <label>Тип скважины
          <select
            value={cond.hole_kinds[0] ?? ""}
            onChange={(e) => onPatchCondition({ hole_kinds: e.target.value ? [e.target.value] : [] })}
          >
            <option value="">любой</option>
            {Object.entries(HOLE_KIND_LABELS).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </label>
        <label>Ряды (через запятую)
          <input
            type="text"
            value={cond.rows.join(", ")}
            onChange={(e) => onPatchCondition({
              rows: e.target.value.split(/[,\s]+/).map((item) => Number(item)).filter((item) => Number.isFinite(item)),
            })}
            placeholder="все"
          />
        </label>
        <div className="field-pair">
          <label>Глубина от, м
            <input type="number" step="0.1" value={cond.depth_min_m ?? ""} onChange={(e) => onPatchCondition({ depth_min_m: optionalNumber(e.target.value) })} />
          </label>
          <label>до, м
            <input type="number" step="0.1" value={cond.depth_max_m ?? ""} onChange={(e) => onPatchCondition({ depth_max_m: optionalNumber(e.target.value) })} />
          </label>
        </div>
        <div className="field-pair">
          <label>Диаметр от, мм
            <input type="number" step="1" value={cond.diameter_min_mm ?? ""} onChange={(e) => onPatchCondition({ diameter_min_mm: optionalNumber(e.target.value) })} />
          </label>
          <label>до, мм
            <input type="number" step="1" value={cond.diameter_max_mm ?? ""} onChange={(e) => onPatchCondition({ diameter_max_mm: optionalNumber(e.target.value) })} />
          </label>
        </div>
        <div className="field-pair">
          <label>ЛНС от, м
            <input type="number" step="0.1" value={cond.burden_min_m ?? ""} onChange={(e) => onPatchCondition({ burden_min_m: optionalNumber(e.target.value) })} />
          </label>
          <label>до, м
            <input type="number" step="0.1" value={cond.burden_max_m ?? ""} onChange={(e) => onPatchCondition({ burden_max_m: optionalNumber(e.target.value) })} />
          </label>
        </div>
        <div className="field-pair">
          <label>Шаг от, м
            <input type="number" step="0.1" value={cond.spacing_min_m ?? ""} onChange={(e) => onPatchCondition({ spacing_min_m: optionalNumber(e.target.value) })} />
          </label>
          <label>до, м
            <input type="number" step="0.1" value={cond.spacing_max_m ?? ""} onChange={(e) => onPatchCondition({ spacing_max_m: optionalNumber(e.target.value) })} />
          </label>
        </div>
        <div className="field-pair">
          <label>До откоса от, м
            <input type="number" step="0.1" value={cond.distance_to_face_min_m ?? ""} onChange={(e) => onPatchCondition({ distance_to_face_min_m: optionalNumber(e.target.value) })} />
          </label>
          <label>до, м
            <input type="number" step="0.1" value={cond.distance_to_face_max_m ?? ""} onChange={(e) => onPatchCondition({ distance_to_face_max_m: optionalNumber(e.target.value) })} />
          </label>
        </div>
        <label>Интервал по стволу
          <select value={cond.geological_interval} onChange={(e) => onPatchCondition({ geological_interval: e.target.value })}>
            {Object.entries(GEOLOGICAL_INTERVAL_LABELS).map(([value, label]) => (
              <option key={value || "any"} value={value}>{label}</option>
            ))}
          </select>
        </label>
        <label>Домен
          <select
            value={cond.rock_domain_ids[0] ?? ""}
            onChange={(e) => onPatchCondition({ rock_domain_ids: e.target.value ? [e.target.value] : [] })}
          >
            <option value="">любой</option>
            {domains.map((domain) => <option key={domain.id} value={domain.id}>{domain.name}</option>)}
          </select>
        </label>
        <label>Вода
          <select value={cond.water} onChange={(e) => onPatchCondition({ water: e.target.value })}>
            {WATER_OPTIONS.map((opt) => <option key={opt.value || "any"} value={opt.value}>{opt.label}</option>)}
          </select>
        </label>
        <div className="field-pair">
          <label>Целевой q от
            <input type="number" step="0.01" value={cond.target_pf_min ?? ""} onChange={(e) => onPatchCondition({ target_pf_min: optionalNumber(e.target.value) })} />
          </label>
          <label>до
            <input type="number" step="0.01" value={cond.target_pf_max ?? ""} onChange={(e) => onPatchCondition({ target_pf_max: optionalNumber(e.target.value) })} />
          </label>
        </div>
      </details>

      {template.actions.map((action, index) => (
        <div key={index} className="template-action">
          <label>Компонент
            <select value={action.kind} onChange={(e) => onPatchAction(index, { kind: e.target.value })}>
              {ACTION_KINDS.map((kind) => <option key={kind} value={kind}>{DECK_KIND_LABELS[kind]}</option>)}
            </select>
          </label>
          <label>Продукт / ВВ
            <select value={action.explosive_key} onChange={(e) => onPatchAction(index, { explosive_key: e.target.value, product: e.target.value })}>
              <option value="">по умолчанию</option>
              {explosives.map((item) => <option key={item.key} value={item.name}>{item.name}</option>)}
              {!explosives.some((item) => item.name === action.explosive_key) && action.explosive_key && (
                <option value={action.explosive_key}>{action.explosive_key}</option>
              )}
            </select>
          </label>
          <label>Участок
            <select value={action.region} onChange={(e) => onPatchAction(index, { region: e.target.value })}>
              {Object.entries(CHARGE_REGION_LABELS).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </label>
          <label>Длина, м
            <input type="number" min="0" step="0.1" value={action.length_m ?? ""} onChange={(e) => onPatchAction(index, { length_m: optionalNumber(e.target.value) })} />
          </label>
          <label className="checkbox-row">
            <input type="checkbox" checked={action.place_primer} onChange={(e) => onPatchAction(index, { place_primer: e.target.checked })} />
            ставить боевик
          </label>
          {template.actions.length > 1 && (
            <button type="button" className="secondary-button" onClick={() => onRemoveAction(index)}>Убрать действие</button>
          )}
        </div>
      ))}
      <button type="button" className="secondary-button" onClick={onAddAction}>Ещё действие</button>
      <label>Заметка
        <input type="text" value={template.notes} onChange={(e) => onPatch({ notes: e.target.value })} />
      </label>
    </div>
  );
}
