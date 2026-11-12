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
    },
  },
}));

import { api } from "../../../../api/endpoints";
import type { LayerAvailability, LayerKind } from "../../../../types/massBlast";
import { layer, projectV2 } from "../testFixtures";
import { DayTab } from "./DayTab";

afterEach(cleanup);

function available(open: Partial<Record<LayerKind, string>> = {}): LayerAvailability[] {
  const labels: Record<LayerKind, string> = {
    NARYAD: "Наряд-путёвка", NOTIFICATION: "Уведомление о массовом взрыве", READINESS_ACT: "Акт готовности блока к заряжанию",
    TALON: "Талон-допуск", ACCEPTANCE_ACT: "Акт приёмки выполненных работ", EXECUTION: "Таблица параметров (исполнительная) и Г.1 по съёмке",
  };
  return (Object.keys(labels) as LayerKind[]).map((kind) => ({
    kind, label: labels[kind], can_open: !(kind in open), reason: open[kind] ?? "", multiple: kind === "NARYAD" || kind === "NOTIFICATION", count: 0,
  }));
}

beforeEach(() => {
  vi.mocked(api.massBlast.layers).mockReset().mockResolvedValue([layer()]);
  vi.mocked(api.massBlast.layersAvailable).mockReset().mockResolvedValue(available({ TALON: "«Талон-допуск» открывается после отметки взрыва." }));
  vi.mocked(api.massBlast.addressees).mockReset().mockResolvedValue({
    registry: true,
    items: [{ code: "N1", label: "Гостехнадзору (эл. почта, за 2 сут.)", taken: true }, { code: "N2", label: "Главе посёлка (письмо, за 1 сут.)", taken: false }],
  });
  vi.mocked(api.massBlast.saveLayer).mockReset().mockImplementation(async (_id, body) => layer({ payload: body.payload, version: 3 }));
});

const approved = projectV2({ lifecycle_status: "approved", current_revision_id: "r1" });

describe("слои дня взрыва", () => {
  it("запас меняет «к выдаче» сразу, в сохранение уходит числом", async () => {
    const user = userEvent.setup();
    render(<DayTab project={approved} />);
    const reserve = await screen.findByLabelText("Запас: ВВ");
    // Запас справочника у ПД — подсказкой; «к выдаче» = проект + запас.
    expect((screen.getByLabelText("Запас: ПД") as HTMLInputElement).placeholder).toBe("2 (справочник)");
    await user.type(reserve, "50,5");
    const row = reserve.closest("tr")!;
    expect(within(row).getByText("1 050,5")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Сохранить" }));
    await waitFor(() => expect(api.massBlast.saveLayer).toHaveBeenCalled());
    const [, body] = vi.mocked(api.massBlast.saveLayer).mock.calls[0];
    expect(body.expected_version).toBe(2);
    expect(body.payload.reserve).toEqual({ "explosive:ВВ:": 50.5 });
  });

  it("открытие другого слоя не стирает несохранённый запас наряда", async () => {
    const user = userEvent.setup();
    vi.mocked(api.massBlast.createLayer).mockResolvedValue(layer({ id: "r1", kind: "READINESS_ACT" }));
    render(<DayTab project={approved} />);
    await user.type(await screen.findByLabelText("Запас: ВВ"), "50");
    // Список перечитывается с новыми объектами слоёв той же версии.
    vi.mocked(api.massBlast.layers).mockResolvedValue([layer()]);
    await user.click(screen.getByRole("button", { name: "Открыть «Акт готовности блока к заряжанию»" }));
    await waitFor(() => expect(api.massBlast.layers).toHaveBeenCalledTimes(2));
    expect((screen.getByLabelText("Запас: ВВ") as HTMLInputElement).value).toBe("50");
  });

  it("выпуск «Факта» обновляет замечания наряда без перезагрузки вкладки", async () => {
    const user = userEvent.setup();
    const execution = layer({ id: "e1", kind: "EXECUTION", payload: {}, view: { blocks: [] } });
    vi.mocked(api.massBlast.layers).mockResolvedValue([layer(), execution]);
    vi.mocked(api.massBlast.issueLayer).mockReset().mockResolvedValue({ id: "er1", layer_id: "e1", revision_no: 1, project_revision_id: "r1", content_sha256: "", created_at: "" });
    render(<DayTab project={projectV2({ lifecycle_status: "executed", current_revision_id: "r1" })} />);
    await screen.findByLabelText("Запас: ВВ");
    vi.mocked(api.massBlast.layers).mockResolvedValue([
      layer({ issues: [{ level: "warning", code: "fact_layer_stale", message: "Выпущена новая ревизия слоя «Факт».", path: "seed.fact" }] }),
      { ...execution, status: "issued", current_revision_id: "er1" },
    ]);
    const factCard = screen.getByText("Таблица параметров (исполнительная) и Г.1 по съёмке").closest("fieldset")!;
    await user.click(within(factCard as HTMLElement).getByRole("button", { name: "Выпустить ревизию" }));
    expect(await screen.findByText("Выпущена новая ревизия слоя «Факт».")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Перенести данные заново" })).toBeTruthy();
  });

  it("графы после взрыва — только когда взрыв произведён", async () => {
    const { unmount } = render(<DayTab project={approved} />);
    await screen.findByLabelText("Запас: ВВ");
    expect(screen.queryByLabelText("Выдано: ВВ")).toBeNull();
    unmount();
    render(<DayTab project={projectV2({ lifecycle_status: "executed", current_revision_id: "r1" })} />);
    expect(await screen.findByLabelText("Выдано: ВВ")).toBeTruthy();
    expect(screen.getByLabelText("Израсходовано: ВВ")).toBeTruthy();
  });

  it("слой, который ещё нельзя открыть, показывает причину", async () => {
    render(<DayTab project={approved} />);
    expect(await screen.findByText("«Талон-допуск» открывается после отметки взрыва.")).toBeTruthy();
  });

  it("уведомление: адресат с уведомлением в список не попадает", async () => {
    const user = userEvent.setup();
    vi.mocked(api.massBlast.createLayer).mockResolvedValue(layer({ id: "n2", kind: "NOTIFICATION" }));
    render(<DayTab project={approved} />);
    const select = await screen.findByLabelText("Адресат из справочника карьера");
    const options = within(select).getAllByRole("option").map((item) => item.textContent);
    expect(options).toEqual(["— выберите —", "Главе посёлка (письмо, за 1 сут.)"]);
    await user.selectOptions(select, "N2");
    await user.click(screen.getByRole("button", { name: "Создать уведомление" }));
    await waitFor(() => expect(api.massBlast.createLayer).toHaveBeenCalledWith("p1", { kind: "NOTIFICATION", payload: { notification_code: "N2" } }));
  });

  it("перенос заново: сначала расхождение, перенос — только после подтверждения", async () => {
    const user = userEvent.setup();
    vi.mocked(api.massBlast.layers).mockResolvedValue([layer({ stale: true, issues: [{ level: "warning", code: "layer_stale", message: "Проект перевыпущен.", path: "" }] })]);
    vi.mocked(api.massBlast.refreshLayer).mockReset()
      .mockResolvedValueOnce({ applied: false, layer: layer(), changes: [{ path: "project.blast_time", label: "Время взрыва", before_text: "13:00", after_text: "14:00" }] })
      .mockResolvedValueOnce({ applied: true, layer: layer({ version: 3 }), changes: [] });
    render(<DayTab project={approved} />);
    await user.click(await screen.findByRole("button", { name: "Перенести данные заново" }));
    const table = await screen.findByRole("table", { name: "Расхождение переноса" });
    expect(within(table).getByText("Время взрыва")).toBeTruthy();
    expect(within(table).getByText("14:00")).toBeTruthy();
    expect(api.massBlast.refreshLayer).toHaveBeenCalledWith("l1", { expected_version: 2, confirm: false });
    // Правка, сделанная при открытом расхождении, сохраняется до переноса.
    await user.type(screen.getByLabelText("Запас: ВВ"), "7");
    await user.click(screen.getByRole("button", { name: "Подтвердить перенос" }));
    await waitFor(() => expect(api.massBlast.refreshLayer).toHaveBeenLastCalledWith("l1", { expected_version: 3, confirm: true }));
    expect(vi.mocked(api.massBlast.saveLayer).mock.calls[0][1].payload.reserve).toEqual({ "explosive:ВВ:": 7 });
    expect(await screen.findByText(/перенесены заново; введённое вручную сохранено/)).toBeTruthy();
  });
});
