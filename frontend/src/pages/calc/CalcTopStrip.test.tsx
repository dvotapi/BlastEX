// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CalcTopStrip, ReferenceWarnings } from "./CalcTopStrip";

afterEach(cleanup);

const UNITS = [
  { code: "UNIT_PERM", name: "Юнит Пермь" },
  { code: "UNIT_URAL", name: "Юнит Урал" },
];

const OBJECTS = [
  { name: "Карьер Анна", production_unit_code: "UNIT_PERM" },
  { name: "Карьер Ломовской", production_unit_code: "UNIT_URAL" },
  { name: "Карьер без юнита", production_unit_code: null },
];

function renderStrip(overrides: Partial<Parameters<typeof CalcTopStrip>[0]> = {}) {
  const props = {
    variant: "page" as const,
    objectName: "Карьер Анна",
    objects: OBJECTS,
    units: UNITS,
    unitCode: "",
    onUnitChange: vi.fn(),
    onObjectChange: vi.fn(),
    autosaveStatus: "idle" as const,
    workspaceLoading: false,
    ...overrides,
  };
  render(<CalcTopStrip {...props} />);
  return props;
}

const optionNames = (label: string) =>
  within(screen.getByLabelText(label)).getAllByRole("option").map((option) => option.textContent);

describe("CalcTopStrip", () => {
  it("выбранный юнит оставляет в списке его объекты и объекты без юнита", () => {
    renderStrip({ unitCode: "UNIT_PERM" });
    expect(optionNames("Объект")).toEqual(["Карьер Анна", "Карьер без юнита"]);
  });

  it("текущий объект чужого юнита не пропадает из списка", () => {
    renderStrip({ unitCode: "UNIT_PERM", objectName: "Карьер Ломовской" });
    expect(optionNames("Объект")).toEqual(["Карьер Анна", "Карьер Ломовской", "Карьер без юнита"]);
    expect(screen.getByLabelText("Объект")).toHaveValue("Карьер Ломовской");
  });

  it("без юнитов в справочнике поле «Юнит» не показывается", () => {
    renderStrip({ units: [] });
    expect(screen.queryByLabelText("Юнит")).toBeNull();
    expect(optionNames("Объект")).toEqual(OBJECTS.map((o) => o.name));
  });

  it("смена юнита и объекта уходит наверх", () => {
    const props = renderStrip();
    expect(optionNames("Юнит")).toEqual(["Все юниты", "Юнит Пермь", "Юнит Урал"]);
    fireEvent.change(screen.getByLabelText("Юнит"), { target: { value: "UNIT_URAL" } });
    expect(props.onUnitChange).toHaveBeenCalledWith("UNIT_URAL");
    fireEvent.change(screen.getByLabelText("Объект"), { target: { value: "Карьер без юнита" } });
    expect(props.onObjectChange).toHaveBeenCalledWith("Карьер без юнита");
  });

  it("предупреждения справочников закрываются кликом мимо и по Esc", () => {
    render(
      <div>
        <button type="button">Порода</button>
        <ReferenceWarnings warnings={["Раздел «Породы» пуст"]} />
      </div>,
    );
    const details = screen.getByText("Предупреждения справочников (1)").closest("details")!;
    details.open = true;
    fireEvent.pointerDown(screen.getByText("Раздел «Породы» пуст"));
    expect(details.open).toBe(true);
    fireEvent.pointerDown(screen.getByRole("button", { name: "Порода" }));
    expect(details.open).toBe(false);
    details.open = true;
    fireEvent.keyDown(document, { key: "Escape" });
    expect(details.open).toBe(false);
  });

  it("без предупреждений строки в заголовке нет", () => {
    render(<ReferenceWarnings warnings={[]} />);
    expect(screen.queryByText(/Предупреждения справочников/)).toBeNull();
  });

  it("команда в шапке больше не показывается", () => {
    renderStrip();
    expect(screen.queryByText("Команда")).toBeNull();
  });
});
