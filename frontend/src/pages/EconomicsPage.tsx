import { useEffect, useMemo, useState } from "react";
import { api } from "../api/endpoints";
import type {
  CapacityChoice,
  CalculationRun,
  EconomicScenario,
  EconomicsReferenceItem,
  EconomicsReferenceSnapshot,
  StoredEconomicScenario,
} from "../types/economics";
import { EconomicsResults } from "./economics/EconomicsResults";
import { ServiceLinesEditor } from "./economics/ServiceLinesEditor";

function emptyScenario(unitCode = ""): EconomicScenario {
  return {
    id: "",
    name: "Новый сценарий",
    description: "",
    production_unit_code: unitCode,
    baseline_service_lines: [],
    candidate_service_lines: [],
    capacity_choices: [],
    reference_revision_id: null,
  };
}

function editableScenario(scenario: EconomicScenario): EconomicScenario {
  // API responses also contain audit metadata. Keep the form payload limited to
  // EconomicScenarioSchema, whose backend contract deliberately forbids extras.
  return {
    id: scenario.id,
    name: scenario.name,
    description: scenario.description,
    production_unit_code: scenario.production_unit_code,
    baseline_service_lines: scenario.baseline_service_lines,
    candidate_service_lines: scenario.candidate_service_lines,
    capacity_choices: scenario.capacity_choices,
    reference_revision_id: scenario.reference_revision_id,
  };
}

function payloadText(item: EconomicsReferenceItem, key: string, fallback = "—"): string {
  const value = item.payload[key];
  return value === null || value === undefined || value === "" ? fallback : String(value);
}

export function EconomicsPage() {
  const [references, setReferences] = useState<EconomicsReferenceSnapshot | null>(null);
  const [scenarios, setScenarios] = useState<StoredEconomicScenario[]>([]);
  const [draft, setDraft] = useState<EconomicScenario>(emptyScenario());
  const [selectedId, setSelectedId] = useState("");
  const [run, setRun] = useState<CalculationRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");

  async function loadInitial() {
    setBusy(true);
    setError("");
    try {
      const [refs, stored] = await Promise.all([
        api.economics.referenceSnapshot(),
        api.economics.scenarios(),
      ]);
      setReferences(refs);
      setScenarios(stored);
      const firstUnit = refs.sections.production_units?.[0]?.code ?? "";
      setDraft(emptyScenario(firstUnit));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось открыть экономическую модель.");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => { void loadInitial(); }, []);

  const packages = references?.sections.work_packages ?? [];
  const operations = references?.sections.operations ?? [];
  const surfaceConditions = references?.sections.bench_surface_conditions ?? [];
  const resourcePools = references?.sections.resource_pools ?? [];
  const productionUnits = references?.sections.production_units ?? [];
  const configuredResources = useMemo(
    () => resourcePools.filter((item) => item.payload.monthly_capacity !== null || Number(item.payload.fixed_cost_rub ?? 0) > 0),
    [resourcePools]
  );

  async function selectScenario(id: string) {
    setSelectedId(id);
    setRun(null);
    if (!id) {
      setDraft(emptyScenario(productionUnits[0]?.code ?? ""));
      return;
    }
    const scenario = scenarios.find((item) => item.id === id) ?? await api.economics.scenario(id);
    setDraft(editableScenario(scenario));
    if (scenario.reference_revision_id && scenario.reference_revision_id !== references?.revision_id) {
      try {
        setReferences(await api.economics.referenceSnapshot(scenario.reference_revision_id));
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "Не удалось загрузить исторические справочники.");
      }
    }
  }

  async function useCurrentReferences() {
    setBusy(true);
    try {
      const current = await api.economics.referenceSnapshot();
      setReferences(current);
      setDraft((value) => ({ ...value, reference_revision_id: current.revision_id }));
      setStatus(`Сценарий перепривязан к ревизии ${current.revision_id}; сохраните его.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось загрузить актуальные справочники.");
    } finally {
      setBusy(false);
    }
  }

  async function save(): Promise<StoredEconomicScenario | null> {
    if (!references) return null;
    if (!draft.name.trim() || !draft.production_unit_code.trim()) {
      setError("Заполните название сценария и код производственного юнита.");
      return null;
    }
    setBusy(true);
    setError("");
    try {
      const payload = {
        ...editableScenario(draft),
        reference_revision_id: draft.reference_revision_id ?? references.revision_id,
      };
      const stored = draft.id
        ? await api.economics.updateScenario(draft.id, payload)
        : await api.economics.createScenario(payload);
      setDraft(editableScenario(stored));
      setSelectedId(stored.id);
      setScenarios((rows) => [stored, ...rows.filter((item) => item.id !== stored.id)]);
      setStatus("Сценарий сохранён.");
      return stored;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось сохранить сценарий.");
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function calculate() {
    const stored = await save();
    if (!stored) return;
    setBusy(true);
    setError("");
    try {
      const calculated = await api.economics.calculateScenario(stored.id);
      setRun(calculated);
      setStatus(`Расчёт ${calculated.id} сохранён.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось рассчитать сценарий.");
    } finally {
      setBusy(false);
    }
  }

  async function clone() {
    if (!draft.id) return;
    setBusy(true);
    setError("");
    try {
      const copy = await api.economics.cloneScenario(draft.id);
      setScenarios((rows) => [copy, ...rows]);
      setDraft(editableScenario(copy));
      setSelectedId(copy.id);
      setRun(null);
      setStatus("Создана копия сценария.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось скопировать сценарий.");
    } finally {
      setBusy(false);
    }
  }

  function updateCapacity(resourceCode: string, patch: Partial<CapacityChoice>) {
    const existing = draft.capacity_choices.find((item) => item.resource_code === resourceCode) ?? {
      resource_code: resourceCode,
      mode: "OVERTIME" as const,
      excess_rate_rub: 0,
      step_capacity: 0,
      step_cost_rub: 0,
    };
    setDraft((current) => ({
      ...current,
      capacity_choices: [
        ...current.capacity_choices.filter((item) => item.resource_code !== resourceCode),
        { ...existing, ...patch },
      ],
    }));
  }

  if (!references) {
    return <div className="page-content"><h2>Экономика юнита</h2>{error ? <div className="page-error">{error}</div> : <p className="page-caption">Загрузка project1…</p>}<button className="secondary-button" onClick={() => void loadInitial()} disabled={busy}>Повторить</button></div>;
  }

  return (
    <div className="page-content economics-page">
      <div className="page-heading">
        <div><h2>Экономика производственного юнита</h2><p>Портфель заказчиков, мощности и внутренняя себестоимость «До / После».</p></div>
        {status && <span className="save-status">{status}</span>}
      </div>
      {error && <div className="page-error">{error}</div>}

      <section className="panel scenario-toolbar">
        <div className="economic-fields-grid">
          <label>Сохранённый сценарий<select value={selectedId} onChange={(e) => void selectScenario(e.target.value)}><option value="">Новый сценарий</option>{scenarios.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
          <label>Название<input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></label>
          <label>Производственный юнит<input list="production-unit-options" value={draft.production_unit_code} onChange={(e) => setDraft({ ...draft, production_unit_code: e.target.value.toUpperCase() })} /><datalist id="production-unit-options">{productionUnits.map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}</datalist></label>
          <label>Ревизия справочников<input value={draft.reference_revision_id ?? references.revision_id} disabled /></label>
        </div>
        <div className="button-row">
          <button onClick={() => { setSelectedId(""); setDraft(emptyScenario(productionUnits[0]?.code ?? "")); setRun(null); }}>Новый</button>
          <button onClick={() => void save()} disabled={busy}>Сохранить</button>
          <button onClick={() => void clone()} disabled={busy || !draft.id}>Копировать</button>
          <button onClick={() => void useCurrentReferences()} disabled={busy}>Актуальные справочники</button>
          <button className="primary-button" onClick={() => void calculate()} disabled={busy}>{busy ? "Выполняется…" : "Рассчитать До / После"}</button>
        </div>
      </section>

      <ServiceLinesEditor
        title="Базовый портфель"
        caption="Действующие заказчики и объёмы производственного юнита."
        lines={draft.baseline_service_lines}
        onChange={(lines) => setDraft({ ...draft, baseline_service_lines: lines })}
        packages={packages}
        operations={operations}
        surfaceConditions={surfaceConditions}
      />
      <ServiceLinesEditor
        title="Добавляемые или изменяемые объекты"
        caption="Новые строки добавляются к базе; при необходимости строка может заменить действующую."
        lines={draft.candidate_service_lines}
        onChange={(lines) => setDraft({ ...draft, candidate_service_lines: lines })}
        packages={packages}
        operations={operations}
        surfaceConditions={surfaceConditions}
        replacementLines={draft.baseline_service_lines}
      />

      <details className="economic-capacity-panel">
        <summary>Поведение при дефиците мощности</summary>
        {configuredResources.length === 0 ? <p className="page-caption">В справочниках ещё не заполнены мощности и постоянные затраты ресурсных пулов.</p> : (
          <div className="table-scroll">
            <table>
              <thead><tr><th>Ресурс</th><th>Мощность/месяц</th><th>Фиксированные затраты</th><th>Решение</th><th>Ставка превышения</th><th>Размер ступени</th><th>Стоимость ступени</th></tr></thead>
              <tbody>{configuredResources.map((resource) => {
                const choice = draft.capacity_choices.find((item) => item.resource_code === resource.code) ?? { resource_code: resource.code, mode: "OVERTIME" as const, excess_rate_rub: 0, step_capacity: 0, step_cost_rub: 0 };
                return <tr key={resource.code}><td>{resource.name}</td><td>{payloadText(resource, "monthly_capacity")}</td><td>{payloadText(resource, "fixed_cost_rub", "0")} ₽</td><td><select value={choice.mode} onChange={(e) => updateCapacity(resource.code, { mode: e.target.value as CapacityChoice["mode"] })}><option value="OVERTIME">Сверхурочно</option><option value="RENT">Аренда</option><option value="SUBCONTRACT">Субподряд</option><option value="NEW_ASSET">Новое ОС</option></select></td><td><input type="number" min="0" value={choice.excess_rate_rub} onChange={(e) => updateCapacity(resource.code, { excess_rate_rub: Number(e.target.value) })} /></td><td><input type="number" min="0" value={choice.step_capacity} onChange={(e) => updateCapacity(resource.code, { step_capacity: Number(e.target.value) })} /></td><td><input type="number" min="0" value={choice.step_cost_rub} onChange={(e) => updateCapacity(resource.code, { step_cost_rub: Number(e.target.value) })} /></td></tr>;
              })}</tbody>
            </table>
          </div>
        )}
      </details>

      {run && <EconomicsResults result={run.result} />}
    </div>
  );
}
