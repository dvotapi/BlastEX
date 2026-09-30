// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { CadImportDialog, type CadImportDialogProps } from "./CadImportDialog";
import { CAD_META, cadEntity, cadSource } from "./testing/fixtures";

const api = vi.hoisted(() => ({
  cad: { meta: vi.fn(), saveRoles: vi.fn(), reparse: vi.fn() },
}));
vi.mock("../../../api/endpoints", () => ({ api }));

afterEach(cleanup);

beforeAll(() => {
  // jsdom не реализует модальный `dialog`.
  HTMLDialogElement.prototype.showModal = vi.fn(function (this: HTMLDialogElement) {
    this.open = true;
  });
  HTMLDialogElement.prototype.close = vi.fn(function (this: HTMLDialogElement) {
    this.open = false;
  });
});

beforeEach(() => {
  api.cad.meta.mockReset().mockResolvedValue(CAD_META);
  api.cad.saveRoles.mockReset();
  api.cad.reparse.mockReset();
});

function renderDialog(extra: Partial<CadImportDialogProps> = {}) {
  const props: CadImportDialogProps = {
    sources: [cadSource()],
    busy: false,
    error: "",
    onSourcesChange: vi.fn(),
    onCancel: vi.fn(),
    onBuild: vi.fn(),
    ...extra,
  };
  render(<CadImportDialog {...props} />);
  return props;
}

async function ready() {
  await screen.findByRole("table", { name: "Слои чертежа" });
}

function highlight(handle: string): Element | null {
  return document.querySelector(`.cad-highlight[data-handle="${handle}"]`);
}

function hit(handle: string): Element {
  const found = document.querySelector(`.cad-hit[data-handle="${handle}"]`);
  if (!found) throw new Error(`нет зоны попадания ${handle}`);
  return found;
}

describe("CadImportDialog", () => {
  it("открывается во весь экран с именем файла и предупреждениями", async () => {
    renderDialog();
    await ready();

    expect(screen.getByRole("dialog", { name: "Импорт чертежа" })).toBeTruthy();
    expect(screen.getByText("блок 66.dwg")).toBeTruthy();
    expect(screen.getByText(/похожи на метры/)).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Слои" }).getAttribute("aria-selected")).toBe("true");
  });

  it("наведение на строку слоя подсвечивает его линии, и наоборот", async () => {
    renderDialog();
    await ready();

    fireEvent.mouseEnter(screen.getByRole("row", { name: /Горизонт \+410/ }));
    expect(highlight("6C3")?.classList.contains("is-hovered")).toBe(true);
    expect(highlight("769")).toBeNull();

    fireEvent.mouseLeave(screen.getByRole("row", { name: /Горизонт \+410/ }));
    fireEvent.mouseEnter(hit("769"));
    expect(screen.getByRole("row", { name: /блок 66 вар 2/ }).classList.contains("is-hovered")).toBe(true);
  });

  it("щелчок по линии раскрывает слой и выделяет её строку", async () => {
    renderDialog();
    await ready();

    fireEvent.click(hit("733"));

    const row = await screen.findByRole("row", { name: /733/ });
    expect(row.classList.contains("is-selected")).toBe(true);
    expect(highlight("733")?.classList.contains("is-selected")).toBe(true);
  });

  it("смена роли слоя сохраняется на сервере, ответ без геометрии сливается в источник", async () => {
    const source = cadSource();
    const layers = source.layers.map((layer) =>
      layer.name === "Горизонт +410" ? { ...layer, role: "ignore" as const, origin: "manual" as const } : layer,
    );
    api.cad.saveRoles.mockResolvedValue({
      id: "src-1",
      template_saved: true,
      floor_z_m: 410,
      warnings: [],
      layers,
      roles: { "6C3": ["ignore", "manual"], "733": ["ignore", "manual"] },
    });
    const props = renderDialog({ sources: [source] });
    await ready();

    fireEvent.change(within(screen.getByRole("row", { name: /Горизонт \+410/ })).getByRole("combobox"), {
      target: { value: "ignore" },
    });

    await waitFor(() => expect(props.onSourcesChange).toHaveBeenCalled());
    expect(api.cad.saveRoles).toHaveBeenCalledWith("src-1", { layers: { "Горизонт +410": "ignore" } });
    const [merged] = (props.onSourcesChange as ReturnType<typeof vi.fn>).mock.calls[0][0];
    const crest = merged.entities.find((item: { handle: string }) => item.handle === "6C3");
    expect([crest.role, crest.role_origin]).toEqual(["ignore", "manual"]);
    expect(crest.points).toEqual(source.entities[0].points);
    expect(merged.layers).toEqual(layers);
    expect(merged.warnings).toEqual([]);
  });

  it("ошибка сохранения видна в окне", async () => {
    api.cad.saveRoles.mockRejectedValue(new Error("Роль «x» неизвестна."));
    renderDialog();
    await ready();

    fireEvent.change(within(screen.getByRole("row", { name: /Отметка/ })).getByRole("combobox"), {
      target: { value: "ignore" },
    });

    expect(await screen.findByText("Роль «x» неизвестна.")).toBeTruthy();
  });

  it("предложенный масштаб применяется повторным разбором", async () => {
    const scaled = cadSource({ params: { scale: 0.001, label_radius_m: 3, floor_z_m: null, bench_height_m: 10 } });
    api.cad.reparse.mockResolvedValue(scaled);
    const props = renderDialog({
      sources: [cadSource({ suggested_scale: 0.001, warnings: [{ code: "units_mm", message: "Похоже на миллиметры.", level: "warning" }] })],
    });
    await ready();

    fireEvent.click(screen.getByRole("button", { name: /масштаб 0,001/ }));

    await waitFor(() => expect(props.onSourcesChange).toHaveBeenCalledWith([scaled]));
    expect(api.cad.reparse).toHaveBeenCalledWith("src-1", { scale: 0.001, label_radius_m: 3, floor_z_m: null, bench_height_m: 10 });
  });

  it("подошва из имени слоя не уходит в повторный разбор как явная", async () => {
    // На чертеже с «Горизонт +410» и «Горизонт +430» явная подошва 410
    // перераспределила бы бровки обоих горизонтов вокруг одной отметки.
    api.cad.reparse.mockResolvedValue(cadSource());
    renderDialog();
    await ready();

    const floor = screen.getByLabelText("Подошва, м") as HTMLInputElement;
    expect(floor.value).toBe("");
    expect(floor.placeholder).toContain("410");

    fireEvent.change(screen.getByLabelText("Радиус подписи, м"), { target: { value: "5" } });
    fireEvent.click(screen.getByRole("button", { name: "Пересчитать" }));

    await waitFor(() => expect(api.cad.reparse).toHaveBeenCalled());
    expect(api.cad.reparse).toHaveBeenCalledWith("src-1", { scale: 1, label_radius_m: 5, floor_z_m: null, bench_height_m: 10 });
  });

  it("явно заданная подошва уходит в повторный разбор", async () => {
    api.cad.reparse.mockResolvedValue(cadSource());
    renderDialog();
    await ready();

    fireEvent.change(screen.getByLabelText("Подошва, м"), { target: { value: "412,5" } });
    fireEvent.click(screen.getByRole("button", { name: "Пересчитать" }));

    await waitFor(() => expect(api.cad.reparse).toHaveBeenCalled());
    expect(api.cad.reparse).toHaveBeenCalledWith("src-1", { scale: 1, label_radius_m: 3, floor_z_m: 412.5, bench_height_m: 10 });
  });

  it("построение по-старому берёт бровки по ролям", async () => {
    const props = renderDialog();
    await ready();

    fireEvent.click(screen.getByRole("button", { name: "Построить блок" }));

    expect(props.onBuild).toHaveBeenCalledWith(
      expect.objectContaining({ fileName: "блок 66.dwg", crest: expect.objectContaining({ handle: "6C3" }), toe: expect.objectContaining({ handle: "733" }) }),
    );
  });

  it("бровки, начерченные отрезками LINE, строятся цепочкой, а не одним отрезком", async () => {
    const piece = (handle: string, layer: string, a: [number, number, number], b: [number, number, number], role: "crest_top" | "crest_bottom") =>
      cadEntity(handle, layer, { kind: "LINE", role, points: [a, b], length_m: Math.hypot(b[0] - a[0], b[1] - a[1]) });
    const source = cadSource({
      entities: [
        piece("A", "верхняя бровка", [0, 0, 420], [10, 0, 420.2], "crest_top"),
        piece("B", "верхняя бровка", [10, 0, 420.2], [20, 5, 420.6], "crest_top"),
        piece("D", "нижняя бровка", [0, -10, 410], [15, -10, 410.4], "crest_bottom"),
        piece("E", "нижняя бровка", [15, -10, 410.4], [30, -12, 410.8], "crest_bottom"),
      ],
      layers: [],
    });
    const props = renderDialog({ sources: [source] });
    await ready();

    fireEvent.click(screen.getByRole("button", { name: "Построить блок" }));

    const choice = (props.onBuild as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(choice.crest.points).toHaveLength(3);
    expect(choice.toe.points).toHaveLength(3);
    // На чертеже подсвечены все отрезки выбранных цепочек.
    expect(["A", "B", "D", "E"].every((handle) => highlight(handle)?.classList.contains("is-emphasized"))).toBe(true);
  });

  it("без пары бровок кнопка неактивна, ошибка построения видна у кнопки", async () => {
    const source = cadSource();
    renderDialog({ sources: [{ ...source, entities: source.entities.filter((item) => item.handle !== "733") }], error: "Контур не построен." });
    await ready();

    fireEvent.change(screen.getByRole("combobox", { name: "Низ" }), { target: { value: "" } });

    expect((screen.getByRole("button", { name: "Построить блок" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByRole("alert").textContent).toContain("Контур не построен.");
  });

  it("кнопка «?» открывает справку окна", async () => {
    renderDialog();
    await ready();

    fireEvent.click(screen.getByRole("button", { name: "Справка по импорту чертежа" }));

    expect((screen.getByRole("dialog", { name: "Импорт чертежа: справка" }) as HTMLDialogElement).open).toBe(true);
  });

  it("закрытие справки не закрывает окно импорта", async () => {
    const props = renderDialog();
    await ready();
    fireEvent.click(screen.getByRole("button", { name: "Справка по импорту чертежа" }));

    // Esc или «×» справки дают событие close у её собственного dialog.
    fireEvent(screen.getByRole("dialog", { name: "Импорт чертежа: справка" }), new Event("close"));

    expect(props.onCancel).not.toHaveBeenCalled();
  });

  it("Отмена закрывает окно", async () => {
    const props = renderDialog();
    await ready();

    fireEvent.click(screen.getByRole("button", { name: "Отмена" }));

    expect(props.onCancel).toHaveBeenCalled();
  });
});
