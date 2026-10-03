// @vitest-environment jsdom
// Группа «Ситуация» панели «Вид» (TASK-013, PR 4): серии ситуации объекта,
// выбор даты версии (только просмотр), слои с цветом DXF и флажком.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { situationLayerKey, type SituationPanelSeries } from "./situationLayer";
import { defaultDesignViewState } from "./viewPresets";
import { VisibilityPanel } from "./VisibilityPanel";

afterEach(cleanup);

const SERIES: SituationPanelSeries[] = [
  {
    key: "положение горных работ",
    title: "Положение горных работ",
    versions: [
      { sourceId: "oct", label: "01.10.2026" },
      { sourceId: "sep", label: "01.09.2026" },
    ],
    displayedId: "oct",
    passportId: "sep",
    layers: [
      { key: situationLayerKey("положение горных работ", "Автодорога"), name: "Автодорога", color: "#3a4540", kindLabel: "Дорога", omitted: false },
      { key: situationLayerKey("положение горных работ", "ВЛ-6кВ"), name: "ВЛ-6кВ", color: "#ff0000", kindLabel: "ЛЭП", omitted: true },
    ],
  },
  {
    key: "блок 70",
    title: "блок 70",
    versions: [{ sourceId: "block", label: "28.09.2026" }],
    displayedId: "block",
    passportId: "block",
    layers: null,
  },
];

function renderPanel(extra: Partial<Parameters<typeof VisibilityPanel>[0]> = {}) {
  const props = {
    viewState: defaultDesignViewState(),
    onPresetChange: vi.fn(),
    onLayerChange: vi.fn(),
    onResetLayers: vi.fn(),
    collapsed: false,
    onToggleCollapsed: vi.fn(),
    situation: { series: SERIES, hidden: new Set<string>(), missing: 0, error: "" },
    onSituationVersion: vi.fn(),
    onSituationLayer: vi.fn(),
    ...extra,
  };
  render(<VisibilityPanel {...props} />);
  return props;
}

describe("VisibilityPanel: ситуация", () => {
  it("серии со слоями, видом и цветом DXF", () => {
    renderPanel();
    const group = screen.getByRole("group", { name: "Ситуация" });

    expect(within(group).getByText("Положение горных работ")).toBeTruthy();
    const road = within(group).getByRole("checkbox", { name: /Автодорога/ }) as HTMLInputElement;
    expect(road.checked).toBe(true);
    expect(within(group).getByText(/Дорога/)).toBeTruthy();
    expect((within(group).getByRole("checkbox", { name: /ВЛ-6кВ/ }) as HTMLInputElement).disabled).toBe(true);
    expect(within(group).getByText(/не уместился/)).toBeTruthy();
    expect(within(group).getByText(/Загружаю/)).toBeTruthy();
  });

  it("дата версии выбирается для просмотра, версия паспорта подписана", () => {
    const props = renderPanel();
    const select = screen.getByRole("combobox", { name: "Версия «Положение горных работ»" }) as HTMLSelectElement;

    expect(select.value).toBe("oct");
    expect(screen.getByText("паспорт: 01.09.2026")).toBeTruthy();
    fireEvent.change(select, { target: { value: "sep" } });
    expect(props.onSituationVersion).toHaveBeenCalledWith("положение горных работ", "sep");
    // У серии из одной версии выбора нет.
    expect(screen.queryByRole("combobox", { name: "Версия «блок 70»" })).toBeNull();
  });

  it("флажок слоя скрывает и показывает его", () => {
    const key = situationLayerKey("положение горных работ", "Автодорога");
    const props = renderPanel({ situation: { series: SERIES, hidden: new Set([key]), missing: 0, error: "" } });
    const road = screen.getByRole("checkbox", { name: /Автодорога/ }) as HTMLInputElement;

    expect(road.checked).toBe(false);
    fireEvent.click(road);
    expect(props.onSituationLayer).toHaveBeenCalledWith(key, true);
  });

  it("поиск слоя ищет и в ситуации", () => {
    renderPanel();
    fireEvent.change(screen.getByRole("searchbox", { name: "Поиск слоя" }), { target: { value: "лэп" } });

    const group = screen.getByRole("group", { name: "Ситуация" });
    expect(within(group).queryByRole("checkbox", { name: /Автодорога/ })).toBeNull();
    expect(within(group).getByRole("checkbox", { name: /ВЛ-6кВ/ })).toBeTruthy();
  });

  it("удалённые версии и ошибка видны", () => {
    renderPanel({ situation: { series: [], hidden: new Set(), missing: 2, error: "Не удалось загрузить ситуацию объекта." } });
    const group = screen.getByRole("group", { name: "Ситуация" });

    expect(within(group).getByText(/Удалено версий, на которые ссылается паспорт: 2/)).toBeTruthy();
    expect(within(group).getByText("Не удалось загрузить ситуацию объекта.")).toBeTruthy();
  });

  it("без ситуации группы нет", () => {
    renderPanel({ situation: { series: [], hidden: new Set(), missing: 0, error: "" } });
    expect(screen.queryByRole("group", { name: "Ситуация" })).toBeNull();
  });
});
