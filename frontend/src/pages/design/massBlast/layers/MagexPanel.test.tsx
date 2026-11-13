// @vitest-environment jsdom
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../../api/endpoints", () => ({
  api: {
    massBlast: {
      layers: vi.fn(),
      layersAvailable: vi.fn(),
      addressees: vi.fn(),
      createLayer: vi.fn(),
      saveLayer: vi.fn(),
      refreshLayer: vi.fn(),
      issueLayer: vi.fn(),
      layerPreviewUrl: (id: string) => `/preview/${id}`,
      layerDocumentUrl: (id: string) => `/doc/${id}`,
      remember: vi.fn(),
      getLayer: vi.fn(),
      magexApprove: vi.fn(),
      magexRetry: vi.fn(),
      magexCancel: vi.fn(),
      magexState: vi.fn(),
      magexAvailability: vi.fn(),
      magexBlasterStatus: vi.fn(),
      magexWarehouses: vi.fn(),
      naryadOptions: vi.fn(),
    },
  },
}));

import { api } from "../../../../api/endpoints";
import type { MagexState, MassBlastLayer } from "../../../../types/massBlast";
import { layer, projectV2 } from "../testFixtures";
import { DayTab } from "./DayTab";
import { canDownload } from "./MagexPanel";

afterEach(cleanup);

const approved = projectV2({ lifecycle_status: "approved", current_revision_id: "r1" });

function online(state: Partial<MagexState> = {}, changes: Partial<MassBlastLayer> = {}): MassBlastLayer {
  const base = layer(changes);
  return {
    ...base,
    view: {
      ...base.view,
      magex: {
        mode: "ONLINE", versions: [], latest: null, accepted_ver: null, issued: false, locked_fields: [],
        material_names: {}, blaster: { code: "BL-01", name: "Трегубов А. И.", index: "ЮФ60АВ", source: "PROJECT" }, ...state,
      },
    },
  };
}

beforeEach(() => {
  vi.mocked(api.massBlast.layersAvailable).mockReset().mockResolvedValue([]);
  vi.mocked(api.massBlast.addressees).mockReset().mockResolvedValue({ registry: false, items: [] });
  vi.mocked(api.massBlast.magexWarehouses).mockReset().mockResolvedValue([{ value: "wh-1", label: "Склад ВМ № 1" }]);
  vi.mocked(api.massBlast.naryadOptions).mockReset().mockResolvedValue({
    blasters: [{ value: "BL-01", label: "Трегубов А. И. — ЮФ60АВ", fill: { blaster_name: "Трегубов А. И.", blaster_index: "ЮФ60АВ" } }],
    vehicles: [{ value: "V-01", label: "КамАЗ — А123ВС96", fill: { vehicle_model: "КамАЗ 43118", vehicle_plate: "А123ВС96", driver: "Петров П. П." } }],
  });
  vi.mocked(api.massBlast.magexBlasterStatus).mockReset().mockResolvedValue({ blaster: null, reported: true });
  vi.mocked(api.massBlast.magexAvailability).mockReset().mockResolvedValue({
    items: { "explosive:ВВ:": { available: 5000, short: false, shared: false }, "primer:ПД:": { available: 10, short: true, shared: false } },
    calculated_at: "2026-10-14T02:11:00Z", error: "",
  });
});

describe("наряд-путёвка в учёте MagEX", () => {
  it("«Доступно на складе» и нехватка до отправки, «Разрешить» вместо выпуска", async () => {
    vi.mocked(api.massBlast.layers).mockResolvedValue([online()]);
    render(<DayTab project={approved} />);
    const row = (await screen.findByLabelText("Запас: ПД")).closest("tr")!;
    await waitFor(() => expect(within(row).getByText(/не хватает/)).toBeTruthy());
    expect(within((screen.getByLabelText("Запас: ВВ")).closest("tr")!).getByText("5 000")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Выпустить ревизию" })).toBeNull();
    expect(screen.getByRole("button", { name: "Разрешить" })).toBeTruthy();
    expect(screen.getByText(/В MagEX не отправлена/)).toBeTruthy();
    expect(screen.getByLabelText("Склад MagEX")).toBeTruthy();
  });

  it("отказ из-за нехватки — таблица «позиция / нужно / доступно»", async () => {
    const user = userEvent.setup();
    vi.mocked(api.massBlast.layers).mockResolvedValue([online()]);
    vi.mocked(api.massBlast.getLayer).mockResolvedValue(online());
    vi.mocked(api.massBlast.magexApprove).mockResolvedValue({
      ...(online().view.magex as MagexState), outcome: "REJECTED",
      rejection: { code: "INSUFFICIENT_AVAILABLE", message: "Не хватает", details: { lines: [{ material_id: "m1", material: "Сферит-ДП", required: "22.000", available: "10.000" }] } },
    });
    render(<DayTab project={approved} />);
    await user.click(await screen.findByRole("button", { name: "Разрешить" }));
    const table = await screen.findByRole("table", { name: "Нехватка ВМ" });
    expect(within(table).getByText("Сферит-ДП")).toBeTruthy();
    expect(within(table).getByText("22")).toBeTruthy();
    expect(within(table).getByText("10")).toBeTruthy();
    expect(api.massBlast.magexApprove).toHaveBeenCalledWith("l1", { expected_version: 2 });
  });

  it("после выдачи склад, запас и № заблокированы", async () => {
    vi.mocked(api.massBlast.layers).mockResolvedValue([online({
      issued: true, accepted_ver: 1,
      locked_fields: ["magex_warehouse_id", "blaster_code", "blaster_index", "issue_date", "reserve", "number", "admissions_confirmed"],
    })]);
    render(<DayTab project={approved} />);
    expect(((await screen.findByLabelText("Запас: ВВ")) as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByLabelText("№ наряда-путёвки") as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByLabelText("Склад MagEX") as HTMLSelectElement).disabled).toBe(true);
    expect(screen.getByText(/ВМ выданы: склад, взрывник/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Отменить в MagEX" })).toBeNull();
  });

  it("ожидает MagEX: «Повторить сейчас», печати нет", async () => {
    const pending = { ver: 1, status: "PENDING" as const, response_code: null, response: {}, attempts: 1,
      next_attempt_at: "2026-10-14T05:00:30Z", created_at: "", created_by: "", accepted_at: null, layer_revision_id: "lr1" };
    const item = online({ versions: [pending], latest: pending }, { current_revision_id: "lr1", status: "issued" });
    vi.mocked(api.massBlast.layers).mockResolvedValue([item]);
    render(<DayTab project={approved} />);
    expect(await screen.findByText(/Ожидает MagEX/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Повторить сейчас" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Скачать PDF" })).toBeNull();
    expect(canDownload(item)).toBe(false);
    expect(canDownload(online({ versions: [{ ...pending, status: "ACCEPTED" }] }, { current_revision_id: "lr1" }))).toBe(true);
  });

  it("вне учёта MagEX — причина и обычный выпуск", async () => {
    vi.mocked(api.massBlast.layers).mockResolvedValue([online({ mode: "OFFLINE", reason: "Не задан адрес MagEX (MAGEX_API_URL)." })]);
    render(<DayTab project={approved} />);
    expect(await screen.findByText(/Вне учёта MagEX: Не задан адрес MagEX/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Выпустить ревизию" })).toBeTruthy();
    expect(screen.queryByText("Доступно на складе")).toBeNull();
    // Вне учёта индекс взрывника вводится в наряде — он печатается в форме 4.
    expect(screen.getByLabelText("Индивидуальный индекс взрывника")).toBeTruthy();
  });

  it("отмена в MagEX — с причиной", async () => {
    const user = userEvent.setup();
    const accepted = { ver: 1, status: "ACCEPTED" as const, response_code: 200, response: {}, attempts: 1,
      next_attempt_at: null, created_at: "", created_by: "", accepted_at: "2026-10-14T05:00:00Z", layer_revision_id: "lr1" };
    const item = online({ versions: [accepted], latest: accepted, accepted_ver: 1 }, { current_revision_id: "lr1", status: "issued" });
    vi.mocked(api.massBlast.layers).mockResolvedValue([item]);
    vi.mocked(api.massBlast.getLayer).mockResolvedValue(item);
    vi.mocked(api.massBlast.magexCancel).mockResolvedValue(item.view.magex as MagexState);
    render(<DayTab project={approved} />);
    await user.click(await screen.findByRole("button", { name: "Отменить в MagEX" }));
    const confirm = screen.getByRole("button", { name: "Отменить наряд-путёвку" }) as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
    await user.type(screen.getByLabelText("Причина отмены"), "Взрыв перенесён");
    await user.click(confirm);
    await waitFor(() => expect(api.massBlast.magexCancel).toHaveBeenCalledWith("l1", { reason: "Взрыв перенесён" }));
    expect(await screen.findByText(/резерв освобождён/)).toBeTruthy();
  });

  it("строки одной позиции MagEX — нехватка по сумме", async () => {
    const shared = online();
    shared.view.lines = [
      { key: "nsi:A:", kind: "nsi_surface", name: "НСИ 25", unit: "шт", delay_ms: null, project_qty: 7, reserve_qty: 0, reserve_source: "REFERENCE", issue_qty: 7, issue_kg: null },
      { key: "nsi:B:", kind: "nsi_surface", name: "НСИ 25 (2)", unit: "шт", delay_ms: null, project_qty: 7, reserve_qty: 0, reserve_source: "REFERENCE", issue_qty: 7, issue_kg: null },
    ];
    vi.mocked(api.massBlast.layers).mockResolvedValue([shared]);
    vi.mocked(api.massBlast.magexAvailability).mockResolvedValue({
      items: {
        "nsi:A:": { available: 10, short: true, shared: true, material_id: "m" },
        "nsi:B:": { available: 10, short: true, shared: true, material_id: "m" },
      },
      error: "",
    });
    render(<DayTab project={approved} />);
    const row = (await screen.findByLabelText("Запас: НСИ 25")).closest("tr")!;
    await waitFor(() => expect(within(row).getByText(/не хватает/)).toBeTruthy());
  });

  it("графы после взрыва из MagEX — значением в закрытом поле", async () => {
    const done = online({ accepted_ver: 1 }, { payload: { reserve: {}, issued: { "primer:ПД:": 5 }, consumed: {}, returned: {} } });
    done.view.lines = [{ key: "primer:ПД:", kind: "primer", name: "ПД", unit: "шт", delay_ms: null, project_qty: 20, reserve_qty: 2,
      reserve_source: "REFERENCE", issue_qty: 22, issue_kg: 22, issued_qty: 22, issued_source: "MAGEX", consumed_qty: 20,
      consumed_source: "MAGEX", returned_qty: 2, returned_source: "MAGEX" }];
    vi.mocked(api.massBlast.layers).mockResolvedValue([done]);
    render(<DayTab project={projectV2({ lifecycle_status: "executed", current_revision_id: "r1" })} />);
    const issued = (await screen.findByLabelText("Выдано: ПД")) as HTMLInputElement;
    expect(issued.value).toBe("22");
    expect(issued.disabled).toBe(true);
    expect((screen.getByLabelText("Израсходовано: ПД") as HTMLInputElement).value).toBe("20");
  });

  it("версия в очереди — состояние перечитывается само", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const pending = { ver: 1, status: "PENDING" as const, response_code: null, response: {}, attempts: 1,
        next_attempt_at: null, created_at: "", created_by: "", accepted_at: null, layer_revision_id: "lr1" };
      const item = online({ versions: [pending], latest: pending }, { current_revision_id: "lr1", status: "issued" });
      vi.mocked(api.massBlast.layers).mockResolvedValue([item]);
      vi.mocked(api.massBlast.getLayer).mockReset().mockResolvedValue(item);
      render(<DayTab project={approved} />);
      await screen.findByText(/Ожидает MagEX/);
      await vi.advanceTimersByTimeAsync(15000);
      expect(api.massBlast.getLayer).toHaveBeenCalledWith("l1");
    } finally {
      vi.useRealTimers();
    }
  });

  it("взрывник и спецавтомобиль — списками из справочников, выбор подставляет поля", async () => {
    const user = userEvent.setup();
    vi.mocked(api.massBlast.layers).mockResolvedValue([online({ mode: "OFFLINE", reason: "нет адреса" })]);
    vi.mocked(api.massBlast.saveLayer).mockReset().mockImplementation(async (_id, body) => layer({ payload: body.payload, version: 3 }));
    render(<DayTab project={approved} />);
    await screen.findByRole("option", { name: "КамАЗ — А123ВС96" });
    await user.selectOptions(screen.getByLabelText("Спецавтомобиль"), "КамАЗ — А123ВС96");
    expect((screen.getByLabelText("Спецавтомобиль: марка") as HTMLInputElement).value).toBe("КамАЗ 43118");
    expect((screen.getByLabelText("Спецавтомобиль: гос. номер") as HTMLInputElement).value).toBe("А123ВС96");
    expect((screen.getByLabelText("Водитель") as HTMLInputElement).value).toBe("Петров П. П.");
    await user.selectOptions(screen.getByLabelText("Взрывник"), "Трегубов А. И. — ЮФ60АВ");
    expect((screen.getByLabelText("Индивидуальный индекс взрывника") as HTMLInputElement).value).toBe("ЮФ60АВ");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));
    await waitFor(() => expect(api.massBlast.saveLayer).toHaveBeenCalled());
    const [, body] = vi.mocked(api.massBlast.saveLayer).mock.calls[0];
    expect(body.payload).toMatchObject({
      vehicle_code: "V-01", vehicle_model: "КамАЗ 43118", vehicle_plate: "А123ВС96", driver: "Петров П. П.",
      blaster_code: "BL-01", blaster_name: "Трегубов А. И.", blaster_index: "ЮФ60АВ",
    });
  });

  it("строки в кг и в штуках одной позиции — нехватка в штуках MagEX", async () => {
    const mixed = online();
    mixed.view.lines = [
      { key: "vv:kg:", kind: "explosive", name: "Патроны, кг", unit: "кг", delay_ms: null, project_qty: 100, reserve_qty: 0, reserve_source: "REFERENCE", issue_qty: 100, issue_kg: 100 },
      { key: "vv:pcs:", kind: "explosive", name: "Патроны, шт", unit: "шт", delay_ms: null, project_qty: 5, reserve_qty: 0, reserve_source: "REFERENCE", issue_qty: 5, issue_kg: 125 },
    ];
    vi.mocked(api.massBlast.layers).mockResolvedValue([mixed]);
    vi.mocked(api.massBlast.magexAvailability).mockResolvedValue({
      items: {
        "vv:kg:": { available: 250, short: false, shared: true, material_id: "m", available_magex: 10, factor: 1 / 25, whole: true },
        "vv:pcs:": { available: 10, short: false, shared: true, material_id: "m", available_magex: 10, factor: 1, whole: true },
      },
      error: "",
    });
    render(<DayTab project={approved} />);
    // 100 кг = 4 патрона по 25 кг + 5 шт = 9 ≤ 10 — хватает.
    const row = (await screen.findByLabelText("Запас: Патроны, шт")).closest("tr")!;
    await waitFor(() => expect(within(row).getByText(/10/)).toBeTruthy());
    expect(screen.queryByText(/не хватает/)).toBeNull();
  });
});
