// @vitest-environment jsdom
import { render, type RenderResult } from "@testing-library/react";
import type { ReactElement } from "react";
import { WorkspaceContext } from "../app/useWorkspace";

/**
 * Рендер компонента вкладки «Экономика блока» с минимальным контекстом
 * рабочего пространства — вместо реального `WorkspaceProvider`, который
 * ходит в API. Тест переопределяет только нужные ему поля.
 */
export function renderWithWorkspace(
  ui: ReactElement,
  overrides: Partial<{
    canEdit: boolean;
  }> = {},
): RenderResult {
  const value = {
    loading: false,
    error: "",
    state: null,
    scenarios: [],
    activeScenario: null,
    dirty: false,
    saving: false,
    blastContext: null,
    setBlastContext: () => {},
    updateSnapshot: () => {},
    setActiveWorkObjectName: async () => {},
    save: async () => {},
    reload: async () => {},
    canEdit: overrides.canEdit ?? true,
  };
  return render(<WorkspaceContext.Provider value={value}>{ui}</WorkspaceContext.Provider>);
}
