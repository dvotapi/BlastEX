import { ruNumber } from "../../lib/format";
import type {
  BlastDomain,
  BlockContour,
  DataProvenance,
  Hole,
  RockPropertySet,
  WaterCondition,
} from "../../types/design";
import { emptyProvenance, emptyRockProperties } from "../../types/design";

const DOMAIN_COLORS = ["#c4a574", "#6b8f71", "#7a6ee0", "#d0784a", "#4a90a4", "#b85c7a"];

const WATER_OPTIONS: { value: WaterCondition; label: string }[] = [
  { value: "", label: "не задано" },
  { value: "dry", label: "сухо" },
  { value: "moist", label: "влажно" },
  { value: "wet", label: "обводнено" },
  { value: "flowing", label: "приток" },
];

export function nextDomainId(existing: BlastDomain[]): string {
  const used = new Set(existing.map((d) => d.id));
  let index = existing.length + 1;
  while (used.has(`D-${index}`)) index += 1;
  return `D-${index}`;
}

export function emptyDomain(existing: BlastDomain[], name = "Новый домен"): BlastDomain {
  return {
    id: nextDomainId(existing),
    name,
    polygon: [],
    properties: emptyRockProperties(),
    provenance: emptyProvenance("designed"),
    z_top_m: null,
    z_bottom_m: null,
    priority: existing.length,
    color: DOMAIN_COLORS[existing.length % DOMAIN_COLORS.length],
    notes: "",
  };
}

export function exampleLayeredDomains(contour: BlockContour): BlastDomain[] {
  const crest = contour.bench.crest_z_m;
  const polygon = contour.vertices.map((v) => ({ ...v }));
  const layers: Array<{ name: string; top: number; bottom: number; props: Partial<RockPropertySet>; color: string }> = [
    {
      name: "Кора выветривания",
      top: crest,
      bottom: crest - 3,
      color: DOMAIN_COLORS[0],
      props: { fracturing: "weathered", blastability: "high", density_kg_m3: 2200, water_condition: "moist" },
    },
    {
      name: "Гранит монолитный",
      top: crest - 3,
      bottom: crest - 8,
      color: DOMAIN_COLORS[1],
      props: { fracturing: "competent", blastability: "medium", density_kg_m3: 2700, ucs_mpa: 140, rqd_pct: 80 },
    },
    {
      name: "Гранит трещиноватый",
      top: crest - 8,
      bottom: crest - 11,
      color: DOMAIN_COLORS[2],
      props: { fracturing: "intense", blastability: "high", density_kg_m3: 2650, ucs_mpa: 90, rqd_pct: 45 },
    },
  ];
  return layers.map((layer, index) => ({
    id: `D-${index + 1}`,
    name: layer.name,
    polygon,
    properties: { ...emptyRockProperties(), ...layer.props },
    provenance: { ...emptyProvenance("designed"), method: "example_layers" },
    z_top_m: layer.top,
    z_bottom_m: layer.bottom,
    priority: index,
    color: layer.color,
    notes: "Пример слоёв 0–3 / 3–8 / 8–11 м",
  }));
}

export function GeologyPanel({
  domains,
  selectedDomainId,
  onSelectedDomainIdChange,
  drawing,
  onToggleDrawing,
  waterTableZ,
  holes,
  selectedHoleIds,
  busy,
  onUpsert,
  onDelete,
  onCopyContour,
  onExampleLayers,
  onWaterTableChange,
  onIntercept,
}: {
  domains: BlastDomain[];
  selectedDomainId: string | null;
  onSelectedDomainIdChange: (id: string | null) => void;
  drawing: boolean;
  onToggleDrawing: () => void;
  waterTableZ: number | null;
  holes: Hole[];
  selectedHoleIds: Set<string>;
  busy: boolean;
  onUpsert: (domain: BlastDomain) => void;
  onDelete: (id: string) => void;
  onCopyContour: (id: string) => void;
  onExampleLayers: () => void;
  onWaterTableChange: (value: number | null) => void;
  onIntercept: () => void;
}) {
  const selected = domains.find((d) => d.id === selectedDomainId) ?? null;
  const selectedHole = holes.find((h) => selectedHoleIds.has(h.id)) ?? holes[0] ?? null;

  function patchSelected(patch: Partial<BlastDomain>) {
    if (!selected) return;
    onUpsert({ ...selected, ...patch });
  }

  function patchProps(patch: Partial<RockPropertySet>) {
    if (!selected) return;
    onUpsert({ ...selected, properties: { ...selected.properties, ...patch } });
  }

  function patchProvenance(patch: Partial<DataProvenance>) {
    if (!selected) return;
    onUpsert({ ...selected, provenance: { ...selected.provenance, ...patch, role: "designed" } });
  }

  return (
    <section className="panel">
      <header><b>Геология</b><span>02а</span></header>
      <div className="panel-body">
        <small>
          Проектные домены — отдельный слой над поверхностью уступа. Замеренные интервалы скважины
          хранятся отдельно и не подменяют проект.
        </small>

        <div className="geology-list">
          {domains.length === 0 && <div className="surface-card empty"><b>Доменов нет</b><small>добавьте слой или регион</small></div>}
          {domains.map((domain) => (
            <button
              key={domain.id}
              type="button"
              className={`geology-card${domain.id === selectedDomainId ? " active" : ""}`}
              onClick={() => onSelectedDomainIdChange(domain.id)}
            >
              <i style={{ background: domain.color || "#8fa399" }} />
              <div>
                <b>{domain.name || domain.id}</b>
                <small>
                  {domain.polygon.length >= 3 ? `${domain.polygon.length} верш.` : "весь план"}
                  {domain.z_top_m !== null || domain.z_bottom_m !== null
                    ? ` · Z ${fmtBound(domain.z_top_m)}…${fmtBound(domain.z_bottom_m)}`
                    : ""}
                </small>
              </div>
            </button>
          ))}
        </div>

        <div className="plans-actions">
          <button type="button" className="secondary-button" onClick={() => {
            const created = emptyDomain(domains);
            onUpsert(created);
            onSelectedDomainIdChange(created.id);
          }}>Добавить домен</button>
          <button type="button" className="secondary-button" onClick={onExampleLayers}>Пример слоёв</button>
        </div>

        {selected && (
          <>
            <label>
              Название
              <input type="text" value={selected.name} onChange={(e) => patchSelected({ name: e.target.value })} />
            </label>
            <div className="field-pair">
              <label>
                Цвет
                <input type="color" value={selected.color || "#8fa399"} onChange={(e) => patchSelected({ color: e.target.value })} />
              </label>
              <label>
                Приоритет
                <input type="number" step="1" value={selected.priority} onChange={(e) => patchSelected({ priority: Number(e.target.value) })} />
              </label>
            </div>
            <div className="field-pair">
              <label>
                Кровля слоя Z, м
                <input
                  type="number"
                  step="0.1"
                  value={selected.z_top_m ?? ""}
                  placeholder="не ограничена"
                  onChange={(e) => patchSelected({ z_top_m: e.target.value === "" ? null : Number(e.target.value) })}
                />
              </label>
              <label>
                Подошва слоя Z, м
                <input
                  type="number"
                  step="0.1"
                  value={selected.z_bottom_m ?? ""}
                  placeholder="не ограничена"
                  onChange={(e) => patchSelected({ z_bottom_m: e.target.value === "" ? null : Number(e.target.value) })}
                />
              </label>
            </div>
            <small>Пустой полигон действует на весь план. Иначе домен режется по контуру в плане.</small>
            <div className="plans-actions">
              <button type="button" className="secondary-button" onClick={() => onCopyContour(selected.id)}>Взять контур блока</button>
              <button type="button" className={drawing ? "calculate-button" : "secondary-button"} onClick={onToggleDrawing}>
                {drawing ? "Рисуем регион…" : "Рисовать регион"}
              </button>
              <button type="button" className="danger-button" onClick={() => onDelete(selected.id)}>Удалить</button>
            </div>
            {selected.polygon.length > 0 && (
              <small>Вершин региона: {selected.polygon.length}. Клик по плану добавляет точку.</small>
            )}

            <label>
              Плотность, кг/м³
              <input type="number" step="10" value={selected.properties.density_kg_m3 ?? ""} placeholder="SI" onChange={(e) => patchProps({ density_kg_m3: numOrNull(e.target.value) })} />
            </label>
            <div className="field-pair">
              <label>
                UCS, МПа
                <input type="number" step="1" value={selected.properties.ucs_mpa ?? ""} onChange={(e) => patchProps({ ucs_mpa: numOrNull(e.target.value) })} />
              </label>
              <label>
                RQD, %
                <input type="number" step="1" value={selected.properties.rqd_pct ?? ""} onChange={(e) => patchProps({ rqd_pct: numOrNull(e.target.value) })} />
              </label>
            </div>
            <div className="field-pair">
              <label>
                E, ГПа
                <input type="number" step="0.1" value={selected.properties.youngs_modulus_gpa ?? ""} onChange={(e) => patchProps({ youngs_modulus_gpa: numOrNull(e.target.value) })} />
              </label>
              <label>
                ν
                <input type="number" step="0.01" value={selected.properties.poisson_ratio ?? ""} onChange={(e) => patchProps({ poisson_ratio: numOrNull(e.target.value) })} />
              </label>
            </div>
            <div className="field-pair">
              <label>
                Vp, м/с
                <input type="number" step="10" value={selected.properties.p_wave_velocity_m_s ?? ""} onChange={(e) => patchProps({ p_wave_velocity_m_s: numOrNull(e.target.value) })} />
              </label>
              <label>
                Расст. трещин, м
                <input type="number" step="0.1" value={selected.properties.joint_spacing_m ?? ""} onChange={(e) => patchProps({ joint_spacing_m: numOrNull(e.target.value) })} />
              </label>
            </div>
            <div className="field-pair">
              <label>
                Падение, °
                <input type="number" step="1" value={selected.properties.joint_dip_deg ?? ""} onChange={(e) => patchProps({ joint_dip_deg: numOrNull(e.target.value) })} />
              </label>
              <label>
                Направление пад., °
                <input type="number" step="1" value={selected.properties.joint_dip_direction_deg ?? ""} onChange={(e) => patchProps({ joint_dip_direction_deg: numOrNull(e.target.value) })} />
              </label>
            </div>
            <label>
              Трещиноватость
              <input type="text" value={selected.properties.fracturing} onChange={(e) => patchProps({ fracturing: e.target.value })} />
            </label>
            <label>
              Взрываемость
              <input type="text" value={selected.properties.blastability} onChange={(e) => patchProps({ blastability: e.target.value })} />
            </label>
            <label>
              Вода в домене
              <select
                value={selected.properties.water_condition}
                onChange={(e) => patchProps({ water_condition: e.target.value as WaterCondition })}
              >
                {WATER_OPTIONS.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
              </select>
            </label>
            <div className="field-pair">
              <label>
                Источник
                <input type="text" value={selected.provenance.source} onChange={(e) => patchProvenance({ source: e.target.value })} />
              </label>
              <label>
                Метод
                <input type="text" value={selected.provenance.method} onChange={(e) => patchProvenance({ method: e.target.value })} />
              </label>
            </div>
          </>
        )}

        <label>
          Уровень грунтовых вод Z, м
          <input
            type="number"
            step="0.1"
            value={waterTableZ ?? ""}
            placeholder="не задан"
            onChange={(e) => onWaterTableChange(e.target.value === "" ? null : Number(e.target.value))}
          />
        </label>

        <button className="calculate-button" type="button" onClick={onIntercept} disabled={busy || !domains.length || !holes.length}>
          {busy ? "Пересекаем…" : "Пересечь скважины с доменами"}
        </button>
        <small>Заряжание позже прочитает эти интервалы. ML ничего не меняет и не утверждает.</small>

        {selectedHole && (
          <HoleIntervalCard hole={selectedHole} />
        )}
      </div>
    </section>
  );
}

function HoleIntervalCard({ hole }: { hole: Hole }) {
  const length = Math.hypot(hole.toe.x - hole.collar.x, hole.toe.y - hole.collar.y, hole.toe.z - hole.collar.z);
  return (
    <div className="interval-card">
      <b>Интервалы {hole.id}</b>
      {hole.intervals.length === 0 && <small>проектных интервалов нет — пересеките скважины</small>}
      {hole.intervals.map((iv, index) => (
        <div key={`${iv.domain_id}-${index}`} className="interval-row">
          <span>{ruNumber(iv.from_m, 1)}–{ruNumber(iv.to_m, 1)} м</span>
          <span>{iv.domain_name || iv.domain_id || "домен"}</span>
        </div>
      ))}
      {hole.water_intervals.length > 0 && (
        <small>
          Вода (проект): {hole.water_intervals.map((iv) => `${ruNumber(iv.from_m, 1)}–${ruNumber(iv.to_m, 1)} ${waterLabel(iv.condition)}`).join("; ")}
        </small>
      )}
      {hole.measured_intervals.length > 0 && (
        <small>Замерено (не подменяет проект): {hole.measured_intervals.length} инт. из {ruNumber(length, 1)} м</small>
      )}
    </div>
  );
}

function waterLabel(condition: string): string {
  return WATER_OPTIONS.find((opt) => opt.value === condition)?.label || condition;
}

function numOrNull(value: string): number | null {
  return value === "" ? null : Number(value);
}

function fmtBound(value: number | null): string {
  return value === null ? "∞" : ruNumber(value, 1);
}
