import type { ModelParameters } from "../types/blockEconomics";
import type { ScenarioListItem, WorkspaceState } from "../types";

/** Переопределения контекста сметы из снапшота: назначения персонала, смены и
 * подэтапы. Номенклатуру, постоянные расходы и должности сервер берёт из
 * опубликованной ревизии (CalculationContextInputSchema). Цену метра бурения
 * (блок 1.2) модель блока считает по параметрам активного черновика сметы
 * (`drillingParameters`); без них сервер вернёт нулевую цену и пояснение. */
export function buildCostContext(state: WorkspaceState, drillingParameters?: ModelParameters | null) {
  return {
    labor_assignments: state.snapshot.labor_assignment_records,
    ...(drillingParameters ? { drilling_model: { parameters: drillingParameters } } : {}),
    labor_settings: { shifts_per_month: state.snapshot.labor_shifts_per_month },
    scenario_phase_overrides: state.snapshot.scenario_phase_overrides,
  };
}

/** Активные модули сценария с учётом переключателей подэтапов (scenario_phase_overrides). */
export function activeModules(
  scenario: ScenarioListItem | null,
  overrides: Record<string, boolean>
): Set<string> {
  const modules = new Set<string>();
  if (!scenario) return modules;
  for (const phase of scenario.phases) {
    const enabled = overrides[phase.id] ?? phase.enabled;
    if (enabled) phase.modules.forEach((m) => modules.add(m));
  }
  return modules;
}
