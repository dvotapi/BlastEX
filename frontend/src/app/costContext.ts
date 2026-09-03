import type { ScenarioListItem, WorkspaceState } from "../types";

/** Переопределения контекста сметы из снапшота: назначения персонала, ввод
 * бурения, смены и подэтапы. Номенклатуру, постоянные расходы и должности
 * сервер берёт из опубликованной ревизии (CalculationContextInputSchema). */
export function buildCostContext(state: WorkspaceState) {
  return {
    labor_assignments: state.snapshot.labor_assignment_records,
    drilling_input: state.snapshot.drilling_calculator_input,
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
