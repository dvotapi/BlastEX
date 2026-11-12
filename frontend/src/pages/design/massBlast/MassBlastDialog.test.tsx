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
      remember: vi.fn(),
      suggestLayout: vi.fn(),
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
  it("в пустом поле — значение по умолчанию с источником; правка делает его своим, «↺» возвращает", async () => {
    const user = userEvent.setup();
    render(<MassBlastDialog project={projectV2()} onClose={() => {}} onChange={() => {}} />);
    const number = (await screen.findByLabelText("№ проекта")) as HTMLInputElement;
    await waitFor(() => expect(number.value).toBe("66-26/МВ"));
    expect(screen.getByText("правило")).toBeTruthy();
    expect((screen.getByLabelText("Составлен на основании (типовой проект)") as HTMLInputElement).value).toBe("ТП из справочника");
    await user.clear(number);
    await user.type(number, "66-МВ-1");
    expect(number.value).toBe("66-МВ-1");
    await user.click(screen.getByRole("button", { name: /↺ правило: 66-26\/МВ/ }));
    expect(number.value).toBe("66-26/МВ");
  });

  it("«Запомнить для объекта»: заполненное поле, пустое в справочнике, уходит в справочник после сохранения", async () => {
    const user = userEvent.setup();
    vi.mocked(api.me).mockResolvedValue({ email: "lead@example.test", role: "admin" } as never);
    vi.mocked(api.massBlast.remember).mockReset().mockResolvedValue({ revision_id: "r2", fields: ["station"] });
    render(<MassBlastDialog project={projectV2()} onClose={() => {}} onChange={() => {}} />);
    await user.click(await screen.findByRole("button", { name: "Распорядок" }));
    // «станция» уже введена в проекте, в справочнике пусто — галочка включена.
    const box = (await screen.findByRole("checkbox", { name: "Запомнить для объекта" })) as HTMLInputElement;
    expect(box.checked).toBe(true);
    await user.type(screen.getByLabelText("Место укрытия"), "у въезда");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));
    await waitFor(() => expect(api.massBlast.remember).toHaveBeenCalledWith("p1", { paths: ["schedule.station"] }));
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

  it("правки слоя не теряются при переходе на другую вкладку, закрытие спрашивает про них", async () => {
    const user = userEvent.setup();
    const { layer } = await import("./testFixtures");
    vi.mocked(api.massBlast.layers).mockResolvedValue([layer()]);
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const onClose = vi.fn();
    render(<MassBlastDialog project={projectV2({ lifecycle_status: "approved", current_revision_id: "r1" })} onClose={onClose} onChange={() => {}} />);
    await user.type(await screen.findByLabelText("Запас: ВВ"), "50");
    await user.click(screen.getByRole("button", { name: "Реквизиты" }));
    await user.click(screen.getByRole("button", { name: "День взрыва" }));
    expect((screen.getByLabelText("Запас: ВВ") as HTMLInputElement).value).toBe("50");
    await user.click(screen.getByRole("button", { name: "Закрыть" }));
    expect(confirm).toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
    confirm.mockRestore();
  });

  it("предпросмотр с несохранёнными правками блокирует форму, пока идёт сохранение", async () => {
    const user = userEvent.setup();
    let resolve: (value: unknown) => void = () => {};
    vi.mocked(api.massBlast.saveV2).mockImplementation(() => new Promise((done) => { resolve = done; }) as never);
    vi.spyOn(window, "open").mockReturnValue(null);
    render(<MassBlastDialog project={projectV2()} onClose={() => {}} onChange={() => {}} />);
    await user.type(await screen.findByLabelText("№ проекта"), "66-МВ");
    await user.click(screen.getByRole("button", { name: /Проверка и документы/ }));
    await user.click(screen.getByRole("button", { name: "Титул" }));
    await user.click(screen.getByRole("button", { name: "Реквизиты" }));
    expect((screen.getByLabelText("№ проекта") as HTMLInputElement).disabled).toBe(true);
    resolve(projectV2({ version: 4 }));
    await waitFor(() => expect((screen.getByLabelText("№ проекта") as HTMLInputElement).disabled).toBe(false));
  });

  it("изменившийся проект блока снимается заново без правок формы", async () => {
    const user = userEvent.setup();
    vi.mocked(api.massBlast.validateV2).mockResolvedValueOnce(validation({
      valid: false,
      issues: [{ level: "error", code: "stale_source", message: "Источник блока «66» изменился после добавления в проект.", path: "blocks" }],
    }));
    render(<MassBlastDialog project={projectV2()} onClose={() => {}} onChange={() => {}} />);
    await user.click(await screen.findByRole("button", { name: "Обновить снимок блоков" }));
    await waitFor(() => expect(api.massBlast.saveV2).toHaveBeenCalledWith("p1", expect.objectContaining({ expected_version: 3 })));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Обновить снимок блоков" })).toBeNull());
  });

  it("«Запомнить» сохраняет и без других правок формы", async () => {
    const user = userEvent.setup();
    vi.mocked(api.me).mockResolvedValue({ email: "lead@example.test", role: "reference_editor" } as never);
    vi.mocked(api.massBlast.remember).mockReset().mockResolvedValue({ revision_id: "r2", fields: ["station"] });
    render(<MassBlastDialog project={projectV2()} onClose={() => {}} onChange={() => {}} />);
    await screen.findByRole("button", { name: "Распорядок" });
    const saveButton = screen.getByRole("button", { name: "Сохранить" }) as HTMLButtonElement;
    await waitFor(() => expect(saveButton.disabled).toBe(false));
    await user.click(saveButton);
    await waitFor(() => expect(api.massBlast.remember).toHaveBeenCalledWith("p1", { paths: ["schedule.station"] }));
  });

  it("«Предложить посты» без пересечений дорог не трогает посты", async () => {
    const user = userEvent.setup();
    const base = validation();
    vi.mocked(api.massBlast.validateV2).mockResolvedValue({ ...base, context: { ...base.context, graphics: { ...base.context.graphics!, has_situation: true } } });
    vi.mocked(api.massBlast.suggestLayout).mockReset().mockResolvedValue({
      posts: [], points: [{ kind: "blast_station", ref: "", x: -800, y: 0, label: "" }],
      reason: "Дороги ситуации не пересекают границу зоны для людей.",
    });
    render(<MassBlastDialog project={projectV2()} onClose={() => {}} onChange={() => {}} />);
    await user.click(await screen.findByRole("button", { name: "Посты и план" }));
    await user.click(await screen.findByRole("button", { name: "Предложить посты" }));
    expect(await screen.findByText("Дороги ситуации не пересекают границу зоны для людей.")).toBeTruthy();
    expect(screen.getByDisplayValue("дорога")).toBeTruthy();
  });

  it("«Предложить посты» ставит посты и точки в форму", async () => {
    const user = userEvent.setup();
    const base = validation();
    vi.mocked(api.massBlast.validateV2).mockResolvedValue({ ...base, context: { ...base.context, graphics: { ...base.context.graphics!, has_situation: true } } });
    vi.mocked(api.massBlast.suggestLayout).mockReset().mockResolvedValue({
      posts: [{ code: "1", location: "Карьерная дорога, на границе опасной зоны (750 м)" }],
      points: [{ kind: "guard_post", ref: "1", x: 100.5, y: 200, label: "" }, { kind: "blast_station", ref: "", x: -800, y: 0, label: "" }],
      reason: "",
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<MassBlastDialog project={projectV2()} onClose={() => {}} onChange={() => {}} />);
    await user.click(await screen.findByRole("button", { name: "Посты и план" }));
    // Несохранённая правка сохраняется до запроса: посты — по текущим зонам.
    await user.type(screen.getByDisplayValue("дорога"), " у въезда");
    await user.click(await screen.findByRole("button", { name: "Предложить посты" }));
    expect(await screen.findByDisplayValue("Карьерная дорога, на границе опасной зоны (750 м)")).toBeTruthy();
    expect(vi.mocked(api.massBlast.saveV2).mock.invocationCallOrder[0]).toBeLessThan(
      vi.mocked(api.massBlast.suggestLayout).mock.invocationCallOrder[0],
    );
    expect(screen.getByDisplayValue("100,5")).toBeTruthy();
    expect(screen.getByText(/Предложено постов: 1/)).toBeTruthy();
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
