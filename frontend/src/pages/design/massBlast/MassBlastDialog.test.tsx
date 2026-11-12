// @vitest-environment jsdom
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../api/endpoints", () => ({
  api: {
    me: vi.fn(),
    economics: { referenceSchema: vi.fn() },
    massBlast: {
      validateV2: vi.fn(),
      hints: vi.fn(),
      accounts: vi.fn(),
      saveV2: vi.fn(),
      getV2: vi.fn(),
      createRevision: vi.fn(),
      approveRevision: vi.fn(),
      transition: vi.fn(),
      revision: vi.fn(),
      layers: vi.fn(),
      layersAvailable: vi.fn(),
      addressees: vi.fn(),
    },
  },
}));

import { api } from "../../../api/endpoints";
import { MassBlastDialog } from "./MassBlastDialog";
import { installDialog, projectV2, validation } from "./testFixtures";

beforeAll(installDialog);
afterEach(cleanup);

beforeEach(() => {
  vi.mocked(api.me).mockReset().mockResolvedValue({ email: "lead@example.test" } as never);
  vi.mocked(api.economics.referenceSchema).mockReset().mockResolvedValue({
    groups: [],
    sections: {
      blast_safety: {
        json_schema: {
          type: "object",
          properties: {
            k_ground: { type: "number", title: "Коэффициент K_г", "x-unit": "" },
            frost: { type: "boolean", title: "Отрицательная температура" },
          },
        },
      },
      rocks: {
        json_schema: {
          type: "object",
          properties: { hardness_f: { anyOf: [{ type: "number" }, { type: "null" }], "x-unit": "f", description: "Крепость по Протодьяконову; не знаете — оставьте пустым" } },
        },
      },
    },
  } as never);
  vi.mocked(api.massBlast.validateV2).mockReset().mockResolvedValue(validation());
  vi.mocked(api.massBlast.hints).mockReset().mockResolvedValue({
    previous_project_no: "65-МВ", previous_project_date: "2026-11-01", previous_project_name: "",
    personnel_roles: [{ code: "blaster", label: "Взрывник по наряд-путёвке" }],
  });
  vi.mocked(api.massBlast.accounts).mockReset().mockResolvedValue([]);
  vi.mocked(api.massBlast.saveV2).mockReset().mockImplementation(async (_id, input) => projectV2({ ...input, version: 4 } as never));
  vi.mocked(api.massBlast.layers).mockReset().mockResolvedValue([]);
  vi.mocked(api.massBlast.revision).mockReset().mockResolvedValue({ context: {} } as never);
  vi.mocked(api.massBlast.layersAvailable).mockReset().mockResolvedValue([]);
});

describe("окно проекта МВ", () => {
  it("подсказка пустого поля — значение справочника; № прошлого проекта", async () => {
    render(<MassBlastDialog project={projectV2()} onClose={() => {}} onChange={() => {}} />);
    expect(await screen.findByText("из справочника объекта: ТП из справочника")).toBeTruthy();
    expect(await screen.findByText(/№ прошлого проекта объекта: 65-МВ от 01\.11\.2026/)).toBeTruthy();
    expect(screen.getByText("из справочника объекта: Заказчиков З. З.")).toBeTruthy();
  });

  it("сохраняет правку с версией черновика и числом с запятой", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<MassBlastDialog project={projectV2()} onClose={() => {}} onChange={onChange} />);
    await user.click(screen.getByRole("button", { name: "ВМ и СИ" }));
    await user.type(screen.getByLabelText("k разбуривания"), "1,03");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));
    await waitFor(() => expect(api.massBlast.saveV2).toHaveBeenCalled());
    const [, input] = vi.mocked(api.massBlast.saveV2).mock.calls[0];
    expect(input.expected_version).toBe(3);
    expect(input.explosives.reaming_k).toBe(1.03);
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ version: 4 }));
  });

  it("ошибки проверки — на вкладке поля, «К полю» открывает её", async () => {
    vi.mocked(api.massBlast.validateV2).mockResolvedValue(validation({
      valid: false,
      issues: [{ level: "error", code: "blast_station_missing", message: "Укажите место взрывной станции.", path: "schedule.station" }],
    }));
    const user = userEvent.setup();
    render(<MassBlastDialog project={projectV2()} onClose={() => {}} onChange={() => {}} />);
    const tab = await screen.findByRole("button", { name: /Распорядок/ });
    await waitFor(() => expect(within(tab).getByLabelText("ошибок: 1")).toBeTruthy());
    await user.click(screen.getByRole("button", { name: /Проверка и документы/ }));
    await user.click(screen.getByRole("button", { name: "К полю" }));
    expect(screen.getByText("Пункты распорядка")).toBeTruthy();
    expect(screen.getAllByText("Укажите место взрывной станции.").length).toBeGreaterThan(0);
  });

  it("вне черновика форма только для чтения, «День взрыва» — после утверждения", async () => {
    const user = userEvent.setup();
    const { unmount } = render(<MassBlastDialog project={projectV2()} onClose={() => {}} onChange={() => {}} />);
    expect(screen.queryByRole("button", { name: "День взрыва" })).toBeNull();
    unmount();
    render(<MassBlastDialog project={projectV2({ lifecycle_status: "approved", current_revision_id: "r1" })} onClose={() => {}} onChange={() => {}} />);
    expect(await screen.findByRole("button", { name: "День взрыва" })).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Реквизиты" }));
    expect((screen.getByLabelText("№ проекта") as HTMLInputElement).disabled).toBe(true);
    expect(screen.queryByRole("button", { name: "Сохранить" })).toBeNull();
  });

  it("ручные коэффициенты подписаны по схеме справочника, с источником значения", async () => {
    const user = userEvent.setup();
    render(<MassBlastDialog project={projectV2()} onClose={() => {}} onChange={() => {}} />);
    await user.click(await screen.findByRole("button", { name: "Безопасность" }));
    expect(await screen.findByLabelText("Коэффициент K_г")).toBeTruthy();
    expect(screen.getByText(/сейчас: 5 — справочник/)).toBeTruthy();
    expect(screen.getByLabelText("Отрицательная температура").tagName).toBe("SELECT");
    // Поле без заголовка в схеме — подпись из пояснения, а не служебное имя.
    expect(screen.getByLabelText("Крепость по Протодьяконову, f")).toBeTruthy();
    expect(screen.queryByText(/hardness_f/)).toBeNull();
  });

  it("согласовать можно только своей учёткой", async () => {
    const user = userEvent.setup();
    render(<MassBlastDialog project={projectV2({ lifecycle_status: "in_review", current_revision_id: "r1" })} onClose={() => {}} onChange={() => {}} />);
    await user.click(screen.getByRole("button", { name: /Проверка и документы/ }));
    await waitFor(() => expect(api.me).toHaveBeenCalled());
    const mine = await screen.findByRole("button", { name: /Согласовать: ответственный руководитель/ });
    await waitFor(() => expect((screen.getByRole("button", { name: /Согласовать: ответственный за выдачу/ }) as HTMLButtonElement).disabled).toBe(true));
    expect((mine as HTMLButtonElement).disabled).toBe(false);
    await user.click(mine);
    await waitFor(() => expect(api.massBlast.approveRevision).toHaveBeenCalledWith("r1", { role_code: "blast_manager", decision: "approved" }));
  });
});
