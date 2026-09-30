// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { CadImportDialog, type CadImportDialogProps } from "./CadImportDialog";
import { CAD_META, cadSource } from "./testing/fixtures";

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

function line(handle: string): Element {
  const found = document.querySelector(`.cad-line[data-handle="${handle}"]`);
  if (!found) throw new Error(`нет линии ${handle}`);
  return found;
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
    expect(line("6C3").classList.contains("is-hovered")).toBe(true);
    expect(line("769").classList.contains("is-hovered")).toBe(false);

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
    expect(line("733").classList.contains("is-selected")).toBe(true);
  });

  it("смена роли слоя сохраняется на сервере и заменяет источник", async () => {
    const updated = cadSource({ template_saved: true });
    api.cad.saveRoles.mockResolvedValue(updated);
    const props = renderDialog();
    await ready();

    fireEvent.change(within(screen.getByRole("row", { name: /Горизонт \+410/ })).getByRole("combobox"), {
      target: { value: "ignore" },
    });

    await waitFor(() => expect(props.onSourcesChange).toHaveBeenCalledWith([updated]));
    expect(api.cad.saveRoles).toHaveBeenCalledWith("src-1", { layers: { "Горизонт +410": "ignore" } });
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

  it("построение по-старому берёт бровки по ролям", async () => {
    const props = renderDialog();
    await ready();

    fireEvent.click(screen.getByRole("button", { name: "Построить блок" }));

    expect(props.onBuild).toHaveBeenCalledWith(
      expect.objectContaining({ fileName: "блок 66.dwg", crest: expect.objectContaining({ handle: "6C3" }), toe: expect.objectContaining({ handle: "733" }) }),
    );
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
