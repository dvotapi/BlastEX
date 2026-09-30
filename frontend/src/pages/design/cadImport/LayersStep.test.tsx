// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LayersStep, type LayersStepProps } from "./LayersStep";
import { CAD_META, cadEntity, cadSource } from "./testing/fixtures";

afterEach(cleanup);

function renderStep(extra: Partial<LayersStepProps> = {}) {
  const props: LayersStepProps = {
    source: cadSource(),
    meta: CAD_META,
    hover: null,
    selected: null,
    expanded: new Set(),
    disabled: false,
    onToggle: vi.fn(),
    onHover: vi.fn(),
    onSelect: vi.fn(),
    onLayerRole: vi.fn(),
    onEntityRole: vi.fn(),
    ...extra,
  };
  render(<LayersStep {...props} />);
  return props;
}

function layerRow(name: string): HTMLElement {
  return screen.getByRole("row", { name: new RegExp(name.replace(/[+]/g, "\\+")) });
}

describe("LayersStep", () => {
  it("фрагменты слоя свёрнуты в одну строку с числом, диапазоном Z и бейджем", () => {
    const fragments = Array.from({ length: 23 }, (_, index) =>
      cadEntity(`F${index}`, "Горизонт +410", { role: index < 4 ? "crest_bottom" : "crest_top", role_origin: "z" }),
    );
    const source = cadSource();
    renderStep({
      source: {
        ...source,
        entities: fragments,
        layers: [{ ...source.layers[1], entity_count: 23, kinds: { POLYLINE3D: 23 }, z_min: 409.7, z_max: 423 }],
      },
    });

    const row = layerRow("Горизонт +410");
    expect(within(row).getByText(/23 фрагмента/)).toBeTruthy();
    expect(within(row).getByText(/409,7…423,0/)).toBeTruthy();
    expect(within(row).getByText("авто")).toBeTruthy();
    expect((within(row).getByRole("combobox") as HTMLSelectElement).value).toBe("crests_by_z");
    expect(screen.queryAllByRole("row", { name: /F1\b/ })).toHaveLength(0);
  });

  it("точки и подписи слоя считаются отдельно", () => {
    renderStep();
    expect(within(layerRow("Отметка")).getByText(/1 точка · 1 подпись/)).toBeTruthy();
  });

  it("раскрытый слой показывает сущности с ролью и происхождением", () => {
    renderStep({ expanded: new Set(["Горизонт +410"]) });

    const bottom = screen.getByRole("row", { name: /733/ });
    expect(within(bottom).getByText("по Z")).toBeTruthy();
    expect((within(bottom).getByRole("combobox") as HTMLSelectElement).value).toBe("");
    expect(within(bottom).getByRole("option", { name: "По слою: Бровка нижняя" })).toBeTruthy();
  });

  it("роль, унаследованная от ручной роли слоя, показывается как «По слою»", () => {
    const source = cadSource();
    source.entities = source.entities.map((item) =>
      item.handle === "733" ? { ...item, role: "ignore", role_origin: "manual", role_override: false } : item,
    );
    renderStep({ source, expanded: new Set(["Горизонт +410"]) });

    const select = within(screen.getByRole("row", { name: /733/ })).getByRole("combobox") as HTMLSelectElement;
    expect(select.value).toBe("");
    expect(within(select).getByRole("option", { name: "По слою: Не использовать" })).toBeTruthy();
  });

  it("явная роль объекта выбрана в списке", () => {
    const source = cadSource();
    source.entities = source.entities.map((item) =>
      item.handle === "733" ? { ...item, role: "feature_line", role_origin: "manual", role_override: true } : item,
    );
    renderStep({ source, expanded: new Set(["Горизонт +410"]) });

    expect((within(screen.getByRole("row", { name: /733/ })).getByRole("combobox") as HTMLSelectElement).value).toBe("feature_line");
  });

  it("смена роли слоя и сущности уходит наверх", () => {
    const props = renderStep({ expanded: new Set(["Горизонт +410"]) });

    fireEvent.change(within(layerRow("Горизонт +410")).getByRole("combobox"), { target: { value: "ignore" } });
    fireEvent.change(within(screen.getByRole("row", { name: /733/ })).getByRole("combobox"), {
      target: { value: "feature_line" },
    });

    expect(props.onLayerRole).toHaveBeenCalledWith("Горизонт +410", "ignore");
    expect(props.onEntityRole).toHaveBeenCalledWith("733", "feature_line");
  });

  it("точке предлагаются только роли для точек", () => {
    renderStep({ expanded: new Set(["Отметка"]) });

    const options = within(screen.getByRole("row", { name: /51C/ })).getAllByRole("option").map((item) => item.textContent);
    expect(options).toEqual(["По слою: Отметки поверхности", "Отметки поверхности", "Ситуация", "Не использовать"]);
  });

  it("выбранный на чертеже объект виден и за пределами первых 200 строк", () => {
    const many = Array.from({ length: 205 }, (_, index) => cadEntity(`P${index}`, "Отметка", { kind: "POINT", geometry_type: "point" }));
    const source = cadSource();
    renderStep({
      source: { ...source, entities: many, layers: [{ ...source.layers[2], entity_count: 205, kinds: { POINT: 205 } }] },
      expanded: new Set(["Отметка"]),
      selected: { layer: "Отметка", handle: "P204" },
    });

    expect(screen.getByRole("row", { name: /P204/ }).classList.contains("is-selected")).toBe(true);
    expect(screen.queryByRole("row", { name: /P203/ })).toBeNull();
  });

  it("наведение и выбор строки сообщают слой", () => {
    const props = renderStep();

    fireEvent.mouseEnter(layerRow("Отметка"));
    fireEvent.click(within(layerRow("Отметка")).getByRole("button", { name: /Раскрыть/ }));

    expect(props.onHover).toHaveBeenCalledWith({ layer: "Отметка", handle: null });
    expect(props.onToggle).toHaveBeenCalledWith("Отметка");
  });
});
