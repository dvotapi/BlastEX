// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { CadImportDialog, type CadImportDialogProps } from "./CadImportDialog";
import { CAD_META, cadSource, contourResult } from "./testing/fixtures";

const api = vi.hoisted(() => ({
  cad: { meta: vi.fn(), saveRoles: vi.fn(), reparse: vi.fn(), contourLines: vi.fn(), contour: vi.fn(), saveAreaBasis: vi.fn() },
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
  api.cad.contourLines.mockReset().mockResolvedValue({ splits: {}, intersections: [], crests_top: [], crests_bottom: [], gaps: [] });
  api.cad.contour.mockReset().mockResolvedValue(contourResult());
  api.cad.saveAreaBasis.mockReset().mockResolvedValue({ area_basis: "top", saved: true });
});

function renderDialog(extra: Partial<CadImportDialogProps> = {}) {
  const props: CadImportDialogProps = {
    sources: [cadSource()],
    burden: 4,
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
      overrides: ["51C"],
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
    // Признак явной роли — из ответа: унаследованные от слоя роли явными не считаются.
    expect(merged.entities.filter((item: { role_override: boolean }) => item.role_override).map((item: { handle: string }) => item.handle)).toEqual(["51C"]);
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

  it("без ручных действий: готовый контур блока выбран, площади у кнопки", async () => {
    renderDialog();
    await ready();

    await waitFor(() => expect(api.cad.contour).toHaveBeenCalledWith("src-1", { method: "ready", handle: "769", tolerance_m: 0.5 }));
    expect(await screen.findByText(/S верх 2789,9 м²/)).toBeTruthy();
    await waitFor(() => expect((screen.getByRole("button", { name: "Построить блок" }) as HTMLButtonElement).disabled).toBe(false));
  });

  it("«Построить блок» отдаёт контур, свободные рёбра, отметки уступа и данные чертежа", async () => {
    const props = renderDialog();
    await ready();
    const button = screen.getByRole("button", { name: "Построить блок" }) as HTMLButtonElement;
    await waitFor(() => expect(button.disabled).toBe(false));

    fireEvent.click(button);

    const choice = (props.onBuild as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(choice.vertices).toEqual([[90, 170], [140, 170], [140, 215]]);
    expect(choice.free_faces).toEqual([[1, 2]]);
    expect(choice.bench).toMatchObject({ crest_z_m: 420.3, toe_z_m: 410 });
    expect(choice.cad).toMatchObject({
      source_id: "src-1",
      file_name: "блок 66.dwg",
      method: "ready",
      area_top_m2: 2789.93,
      area_bottom_m2: 4120.92,
      map_area_m2: null,
      area_basis: "mean",
      area_m2: 3455.42,
      edited: false,
    });
  });

  it("выбор площади блока доходит до другого файла того же объекта", async () => {
    const second = cadSource({ id: "src-2", file_name: "ситуация.dxf" });
    const props = renderDialog({ sources: [cadSource(), second] });
    await ready();
    fireEvent.click(screen.getByRole("tab", { name: "Контур" }));

    fireEvent.click(within(await screen.findByRole("radiogroup", { name: "Площадь блока" })).getByRole("radio", { name: /S верх/ }));

    const updated = (props.onSourcesChange as ReturnType<typeof vi.fn>).mock.calls.at(-1)?.[0];
    expect(updated.map((source: { area_basis: string }) => source.area_basis)).toEqual(["top", "top"]);
  });

  it("сохранения площади блока уходят по порядку щелчков", async () => {
    const resolvers: Array<() => void> = [];
    api.cad.saveAreaBasis.mockImplementation(
      (_id: string, basis: string) => new Promise((resolve) => resolvers.push(() => resolve({ area_basis: basis, saved: true }))),
    );
    renderDialog();
    await ready();
    fireEvent.click(screen.getByRole("tab", { name: "Контур" }));
    const group = await screen.findByRole("radiogroup", { name: "Площадь блока" });

    fireEvent.click(within(group).getByRole("radio", { name: /S верх/ }));
    fireEvent.click(within(group).getByRole("radio", { name: /S низ/ }));

    await waitFor(() => expect(api.cad.saveAreaBasis).toHaveBeenCalledTimes(1));
    expect(api.cad.saveAreaBasis).toHaveBeenLastCalledWith("src-1", "top");
    resolvers[0]();
    await waitFor(() => expect(api.cad.saveAreaBasis).toHaveBeenCalledTimes(2));
    expect(api.cad.saveAreaBasis).toHaveBeenLastCalledWith("src-1", "bottom");
  });

  it("без объекта работ выбор площади действует только в окне и переживает повторный разбор", async () => {
    const orphan = cadSource({ site_code: "", template_saved: false, suggested_scale: 0.001 });
    api.cad.reparse.mockResolvedValue(cadSource({ site_code: "", template_saved: false, params: { scale: 0.001, label_radius_m: 3, floor_z_m: null, bench_height_m: 10 } }));
    const props = renderDialog({ sources: [orphan] });
    await ready();
    fireEvent.click(screen.getByRole("tab", { name: "Контур" }));
    expect(await screen.findByText(/действует только в этом окне/)).toBeTruthy();
    fireEvent.click(within(screen.getByRole("radiogroup", { name: "Площадь блока" })).getByRole("radio", { name: /S верх/ }));
    fireEvent.click(screen.getByRole("tab", { name: "Слои" }));

    fireEvent.click(screen.getByRole("button", { name: /масштаб 0,001/ }));

    await waitFor(() => expect(api.cad.reparse).toHaveBeenCalled());
    await waitFor(() => {
      const last = (props.onSourcesChange as ReturnType<typeof vi.fn>).mock.calls.at(-1)?.[0];
      expect(last[0].params.scale).toBe(0.001);
      expect(last[0].area_basis).toBe("top");
    });
  });

  it("выбор площади блока сохраняется на объекте и уходит в паспорт", async () => {
    const props = renderDialog();
    await ready();
    fireEvent.click(screen.getByRole("tab", { name: "Контур" }));
    const group = await screen.findByRole("radiogroup", { name: "Площадь блока" });

    fireEvent.click(within(group).getByRole("radio", { name: /S верх/ }));

    await waitFor(() => expect(api.cad.saveAreaBasis).toHaveBeenCalledWith("src-1", "top"));
    const button = screen.getByRole("button", { name: "Построить блок" }) as HTMLButtonElement;
    await waitFor(() => expect(button.disabled).toBe(false));
    fireEvent.click(button);
    const choice = (props.onBuild as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(choice.cad).toMatchObject({ area_basis: "top", area_m2: 2789.93 });
  });

  it("пока сохраняются роли, «Построить блок» неактивна", async () => {
    api.cad.saveRoles.mockReturnValue(new Promise(() => {}));
    renderDialog();
    await ready();
    const button = screen.getByRole("button", { name: "Построить блок" }) as HTMLButtonElement;
    await waitFor(() => expect(button.disabled).toBe(false));

    fireEvent.change(within(screen.getByRole("row", { name: /Отметка/ })).getByRole("combobox"), {
      target: { value: "ignore" },
    });

    await waitFor(() => expect(button.disabled).toBe(true));
  });

  it("самопересечение видно у кнопки, и кнопка неактивна", async () => {
    api.cad.contour.mockResolvedValue(
      contourResult({ ok: false, issues: [{ code: "self_intersection", message: "Контур пересекает сам себя в точке (1,00; 2,00).", point: [1, 2] }], bottom: null }),
    );
    renderDialog();
    await ready();

    expect((await screen.findByRole("alert")).textContent).toContain("пересекает сам себя");
    expect((screen.getByRole("button", { name: "Построить блок" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("предупреждение о высоте уступа видно у кнопки", async () => {
    api.cad.contour.mockResolvedValue(
      contourResult({ warnings: [{ code: "bench_height", message: "Высота уступа 0,6 м вне 2–25 м — проверьте подошву и роли бровок.", level: "warning" }] }),
    );
    renderDialog();
    await ready();

    expect(await screen.findByText(/Высота уступа 0,6 м вне 2–25 м/)).toBeTruthy();
  });

  it("на шаге «Контур» щелчок по линии в сборке добавляет её участок", async () => {
    renderDialog();
    await ready();

    fireEvent.click(screen.getByRole("tab", { name: "Контур" }));
    fireEvent.click(await screen.findByRole("radio", { name: "Сборка" }));
    fireEvent.click(hit("6C3"));

    await waitFor(() =>
      expect(api.cad.contour).toHaveBeenLastCalledWith(
        "src-1",
        expect.objectContaining({ method: "assembly", items: [expect.objectContaining({ kind: "part", handle: "6C3" })] }),
      ),
    );
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
