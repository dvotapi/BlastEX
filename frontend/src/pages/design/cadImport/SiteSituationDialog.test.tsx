// @vitest-environment jsdom
// «Ситуация объекта» (план 2026-11-13): план карьера на все блоки объекта,
// отбор слоёв при загрузке и запоминание выбора на объекте.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import type { CadLayer, CadRolesResponse, CadSiteSources, CadSource } from "../../../types/cad";
import { SiteSituationDialog, type SiteSituationDialogProps } from "./SiteSituationDialog";
import { CAD_META, cadEntity, cadSource } from "./testing/fixtures";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

beforeAll(() => {
  HTMLDialogElement.prototype.showModal = vi.fn(function (this: HTMLDialogElement) {
    this.open = true;
  });
  HTMLDialogElement.prototype.close = vi.fn(function (this: HTMLDialogElement) {
    this.open = false;
  });
});

function layer(name: string, role: "situation" | "ignore", extra: Partial<CadLayer> = {}): CadLayer {
  return {
    name,
    role,
    origin: "auto",
    entity_count: 3,
    kinds: { LWPOLYLINE: 3 },
    z_min: null,
    z_max: null,
    color: null,
    counts_by_role: { [role]: 3 },
    situation_kind: "other",
    situation_kind_origin: "auto",
    hidden: false,
    ...extra,
  };
}

function plan(extra: Partial<CadSource> = {}): CadSource {
  return cadSource({
    id: "plan-1",
    title: "Ситуационный план",
    file_name: "24.09.2026 Ситуационный план.dwg",
    survey_date: "2026-09-24",
    purpose: "situation",
    layers: [
      layer("Дороги", "situation", { situation_kind: "road", hidden: true }),
      layer("Горизонт +410", "situation", { situation_kind: "bench" }),
      layer("Блок 42 факт 05_12_2023", "ignore", { hidden: true }),
    ],
    entities: [
      cadEntity("a1", "Дороги", { role: "situation" }),
      cadEntity("a2", "Горизонт +410", { role: "situation" }),
      cadEntity("a3", "Блок 42 факт 05_12_2023", { role: "ignore" }),
    ],
    ...extra,
  });
}

const LIST: CadSiteSources = {
  site_code: "SITE_ZK",
  truncated: false,
  sources: [
    {
      id: "blk-70",
      title: "граница блока 70",
      file_name: "граница блока 70.dwg",
      survey_date: null,
      uploaded_at: "2026-11-10T10:00:00+00:00",
      uploaded_by: "engineer@example.ru",
      situation_count: 0,
      purpose: "block",
    },
    {
      id: "plan-1",
      title: "Ситуационный план",
      file_name: "24.09.2026 Ситуационный план.dwg",
      survey_date: "2026-09-24",
      uploaded_at: "2026-09-25T10:00:00+00:00",
      uploaded_by: "engineer@example.ru",
      situation_count: 900,
      purpose: "situation",
    },
  ],
};

const META = {
  ...CAD_META,
  situation_kinds: [
    { code: "pit" as const, label: "Контур карьера" },
    { code: "bench" as const, label: "Бровки и откосы" },
    { code: "road" as const, label: "Дорога" },
    { code: "building" as const, label: "Здание" },
    { code: "boundary" as const, label: "Границы" },
    { code: "other" as const, label: "Прочее" },
  ],
};

function renderDialog(extra: Partial<SiteSituationDialogProps> = {}) {
  const props: SiteSituationDialogProps = {
    onClose: vi.fn(),
    onChanged: vi.fn(),
    list: vi.fn(async () => LIST),
    load: vi.fn(async () => plan()),
    upload: vi.fn(async () => ({ sources: [plan()] })),
    saveRoles: vi.fn(),
    loadMeta: vi.fn(async () => META),
    ...extra,
  };
  render(<SiteSituationDialog {...props} />);
  return props;
}

const checkbox = (name: string) => screen.getByRole("checkbox", { name: `Показывать слой «${name}»` }) as HTMLInputElement;

describe("окно «Ситуация объекта»", () => {
  it("открывает самый свежий план карьера объекта, а не чертёж блока", async () => {
    const props = renderDialog();
    await screen.findByText("Ситуационный план");
    expect(props.load).toHaveBeenCalledWith("plan-1");
    expect(checkbox("Дороги").checked).toBe(true);
    expect(checkbox("Блок 42 факт 05_12_2023").checked).toBe(false);
    // Скрытые в чертеже слои помечены: дороги показываются и скрытые.
    expect(screen.getAllByText("скрыт в чертеже")).toHaveLength(2);
    expect(screen.getByText("Показано слоёв: 2 из 3")).toBeTruthy();
    expect((screen.getByRole("combobox", { name: "Вид слоя «Горизонт +410»" }) as HTMLSelectElement).value).toBe("bench");
  });

  it("плана нет — загрузка файла с назначением «ситуация»", async () => {
    const props = renderDialog({ list: vi.fn(async () => ({ ...LIST, sources: [LIST.sources[0]] })) });
    await screen.findByText("Плана карьера ещё нет");
    const input = screen.getByLabelText("Файл плана карьера") as HTMLInputElement;
    const file = new File(["dxf"], "24.09.2026 Ситуационный план.dwg");
    fireEvent.change(input, { target: { files: [file] } });
    await screen.findByText("Ситуационный план");
    expect(props.upload).toHaveBeenCalledWith([file], { purpose: "situation", surveyDate: undefined });
    expect(props.onChanged).toHaveBeenCalled();
  });

  it("сохраняет отбор всех слоёв и изменённые виды — выбор запоминается на объекте", async () => {
    const response: CadRolesResponse = {
      id: "plan-1",
      template_saved: true,
      floor_z_m: null,
      warnings: [],
      layers: [
        layer("Дороги", "situation", { situation_kind: "road", origin: "manual" }),
        layer("Горизонт +410", "ignore", { situation_kind: "bench", origin: "manual" }),
        layer("Блок 42 факт 05_12_2023", "situation", { situation_kind: "boundary", origin: "manual" }),
      ],
      roles: { a2: ["ignore", "manual"], a3: ["situation", "manual"] },
      overrides: [],
    };
    const props = renderDialog({ saveRoles: vi.fn(async () => response) });
    await screen.findByText("Ситуационный план");
    const save = screen.getByRole("button", { name: "Сохранить отбор" }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);

    fireEvent.click(checkbox("Горизонт +410"));
    fireEvent.click(checkbox("Блок 42 факт 05_12_2023"));
    fireEvent.change(screen.getByRole("combobox", { name: "Вид слоя «Блок 42 факт 05_12_2023»" }), { target: { value: "boundary" } });
    expect(save.disabled).toBe(false);
    fireEvent.click(save);

    await screen.findByText("Отбор сохранён и запомнен для объекта.");
    expect(props.saveRoles).toHaveBeenCalledWith("plan-1", {
      layers: { Дороги: "situation", "Горизонт +410": "ignore", "Блок 42 факт 05_12_2023": "situation" },
      kinds: { "Блок 42 факт 05_12_2023": "boundary" },
    });
    expect(props.onChanged).toHaveBeenCalled();
    expect(screen.getAllByText("вручную")).toHaveLength(3);
  });

  it("«Снять все» действует на найденные слои", async () => {
    renderDialog();
    await screen.findByText("Ситуационный план");
    fireEvent.change(screen.getByRole("searchbox", { name: "Найти слой" }), { target: { value: "горизонт" } });
    fireEvent.click(screen.getByRole("button", { name: "Снять все" }));
    fireEvent.change(screen.getByRole("searchbox", { name: "Найти слой" }), { target: { value: "" } });
    expect(checkbox("Горизонт +410").checked).toBe(false);
    expect(checkbox("Дороги").checked).toBe(true);
  });

  it("план из «Чертежей объекта» открывается без поиска", async () => {
    const props = renderDialog({ initialSource: plan({ title: "Старый план" }) });
    expect(await screen.findByText("Старый план")).toBeTruthy();
    expect(props.list).not.toHaveBeenCalled();
  });

  it("без объекта работ — подсказка выбрать объект", async () => {
    renderDialog({ list: vi.fn(async () => ({ site_code: "", sources: [], truncated: false })) });
    await waitFor(() => expect(screen.getByText(/Объект работ не выбран/)).toBeTruthy());
    expect(screen.queryByText("Загрузить план")).toBeNull();
  });

  it("закрытие с несохранённым отбором спрашивает подтверждение", async () => {
    const props = renderDialog();
    await screen.findByText("Ситуационный план");
    fireEvent.click(checkbox("Дороги"));
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    fireEvent.click(screen.getByRole("button", { name: "Закрыть" }));
    expect(confirm).toHaveBeenCalled();
    expect(props.onClose).not.toHaveBeenCalled();
  });
});
