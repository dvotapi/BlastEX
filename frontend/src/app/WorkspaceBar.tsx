import { useState } from "react";
import { useWorkspace } from "./useWorkspace";

export function WorkspaceBar() {
  const { state, activeScenario, dirty, saving, save, setActiveWorkObjectName, updateSnapshot, loading, error } = useWorkspace();
  const [status, setStatus] = useState("");

  if (loading) return <div className="workspace-bar loading">Загрузка рабочего пространства…</div>;
  if (!state) return error ? <div className="page-error">{error}</div> : null;

  async function handleSave() {
    try {
      await save();
      setStatus("Сохранено");
      window.setTimeout(() => setStatus(""), 2500);
    } catch {
      // ошибка уже отражена в контексте
    }
  }

  const phaseOverrides = state.snapshot.scenario_phase_overrides ?? {};
  const warnings = state.warnings ?? [];

  return (
    <div className="workspace-bar">
      <div className="workspace-bar-row">
        <div className="wb-field"><label>Команда</label><b>{state.settings.team_name}</b></div>
        <div className="wb-field">
          <label>Объект работ</label>
          <select value={state.settings.active_work_object_name} onChange={(e) => setActiveWorkObjectName(e.target.value)}>
            {state.references.work_object_records.map((o) => <option key={o.id || o.name} value={o.name}>{o.name}</option>)}
          </select>
        </div>
        <div className="wb-field wb-status">
          <label>Статус</label>
          <span className={dirty ? "dirty" : "clean"}>{status || (dirty ? "есть несохранённые изменения" : "сохранено")}</span>
        </div>
        <div className="wb-actions">
          <button className="primary-button" disabled={saving} onClick={handleSave}>{saving ? "Сохранение…" : "Сохранить"}</button>
        </div>
      </div>
      {error && <div className="page-error">{error}</div>}
      {warnings.length > 0 && (
        <div className="workspace-bar-caption">
          <details>
            <summary>Предупреждения справочников ({warnings.length})</summary>
            <ul>
              {warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          </details>
        </div>
      )}
      {activeScenario && (
        <div className="workspace-bar-caption">
          <span>{activeScenario.calc_profile.ui_caption}</span>
          {activeScenario.phases.length > 1 && (
            <details className="scenario-phases">
              <summary>Подэтапы сценария</summary>
              <ul>
                {activeScenario.phases.map((phase) => (
                  <li key={phase.id}>
                    <label>
                      <input
                        type="checkbox"
                        checked={phaseOverrides[phase.id] ?? phase.enabled}
                        onChange={(e) =>
                          updateSnapshot({
                            scenario_phase_overrides: { ...phaseOverrides, [phase.id]: e.target.checked },
                          })
                        }
                      />
                      {phase.name} — {phase.modules.join(", ")}
                    </label>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </div>
  );
}
