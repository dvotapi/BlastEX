// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { DrillPassportIssue } from "../../../types/drillPassport";
import { passport66, validation66, warning } from "./testFixtures";

const api = vi.hoisted(() => ({
  drillPassport: {
    save: vi.fn(),
    validate: vi.fn(),
    createRevision: vi.fn(),
    get: vi.fn(),
    previewUrl: (id: string) => `/preview/${id}.pdf`,
  },
  economics: { referenceSnapshot: vi.fn() },
}));
const fetchBlob = vi.hoisted(() => vi.fn());
vi.mock("../../../api/endpoints", () => ({ api }));
vi.mock("../../../api/client", async (original) => ({ ...(await original<object>()), fetchBlob }));

import { DrillPassportDialog } from "./DrillPassportDialog";

const SNAPSHOT = {
  revision_id: "ref-1", published_at: null, published_by: "", section_catalog: [], group_catalog: [],
  sections: {
    sites: [{ code: "ZHK", name: "Жуков Камень", payload: {}, is_active: true }],
    equipment_types: [
      { code: "JK830", name: "JK 830-2", payload: { kind: "DRILL_RIG" }, is_active: true },
      { code: "SZM-1", name: "СЗМ", payload: { kind: "SZM" }, is_active: true },
    ],
    drill_passport_profiles: [{ code: "KGOK", name: "Профиль КГОК", payload: {}, is_active: true }],
  },
};

beforeAll(() => {
  // jsdom не реализует модальный `dialog`.
  HTMLDialogElement.prototype.showModal = vi.fn(function (this: HTMLDialogElement) {
    this.open = true;
  });
  HTMLDialogElement.prototype.close = vi.fn(function (this: HTMLDialogElement) {
    this.open = false;
  });
  URL.createObjectURL = vi.fn(() => "blob:preview");
  URL.revokeObjectURL = vi.fn();
});

beforeEach(() => {
  api.drillPassport.save.mockReset().mockImplementation(async (_id, update) => ({
    ...passport66(), passport_no: update.passport_no, payload: update.payload, version: update.expected_version + 1,
  }));
  api.drillPassport.validate.mockReset().mockResolvedValue(validation66());
  api.drillPassport.createRevision.mockReset().mockResolvedValue({ id: "rev-1", revision_no: 1, context: {} });
  api.drillPassport.get.mockReset().mockResolvedValue({ ...passport66(), current_revision_id: "rev-1", version: 5 });
  api.economics.referenceSnapshot.mockReset().mockResolvedValue(SNAPSHOT);
  fetchBlob.mockReset().mockResolvedValue(new Blob(["%PDF"]));
});
afterEach(cleanup);

function open(props: Partial<Parameters<typeof DrillPassportDialog>[0]> = {}) {
  const onChange = vi.fn();
  render(<DrillPassportDialog passport={passport66()} designSaved onClose={vi.fn()} onChange={onChange} {...props} />);
  return { onChange };
}

const releaseButton = () => screen.getByRole("button", { name: "Выпустить ревизию" });

describe("DrillPassportDialog", () => {
  it("пустое поле подписано значением и источником из справочника", async () => {
    open();
    const alpha = await screen.findByLabelText(/Угол откоса рабочего уступа α/);
    await waitFor(() => expect(alpha).toHaveProperty("placeholder", "75° · справочник"));
    expect(screen.getByLabelText(/Вылет оси скважины e/).closest(".drill-field")?.textContent).toContain("вручную");
  });

  it("stakeout_names_invalid — у поля «Блок»", async () => {
    api.drillPassport.validate.mockResolvedValue(
      validation66([{ ...warning("stakeout_names_invalid", "block"), message: "Файл выноса не сформируется: длинный блок." }]),
    );
    open();
    const block = await screen.findByLabelText(/^Блок/);
    await waitFor(() => expect(block.closest(".drill-field")?.textContent).toContain("Файл выноса не сформируется"));
  });

  it("станки — только буровые, объект и профиль — из справочника", async () => {
    open();
    // Пока справочники читаются, поле — текстовое; потом — список.
    await waitFor(() => expect(screen.getByLabelText(/Тип станка/).tagName).toBe("SELECT"));
    const rig = screen.getByLabelText(/Тип станка/);
    expect(within(rig).getByRole("option", { name: "JK 830-2" })).toBeTruthy();
    expect(within(rig).queryByRole("option", { name: /СЗМ/ })).toBeNull();
    expect((screen.getByLabelText(/^Объект$/) as HTMLSelectElement).value).toBe("ZHK");
  });

  it("справочники не прочитаны — коды вводятся текстом", async () => {
    api.economics.referenceSnapshot.mockRejectedValue(new Error("403"));
    open();
    await waitFor(() => expect(api.economics.referenceSnapshot).toHaveBeenCalled());
    const site = await screen.findByLabelText(/^Объект$/);
    await waitFor(() => expect(site.tagName).toBe("INPUT"));
    expect((site as HTMLInputElement).value).toBe("ZHK");
  });

  it("выпуск ждёт отметок «просмотрено» у всех предупреждений", async () => {
    api.drillPassport.validate.mockResolvedValue(validation66([warning("w_max_missing", "w_max_m"), warning("axis_offset_missing")]));
    const user = userEvent.setup();
    const { onChange } = open();
    const boxes = await screen.findAllByRole("checkbox", { name: "просмотрено" });
    expect(boxes).toHaveLength(2);
    expect(releaseButton()).toHaveProperty("disabled", true);
    await user.click(boxes[0]);
    expect(releaseButton()).toHaveProperty("disabled", true);
    await user.click(boxes[1]);
    expect(releaseButton()).toHaveProperty("disabled", false);
    await user.click(releaseButton());
    await waitFor(() => expect(api.drillPassport.createRevision).toHaveBeenCalled());
    expect(api.drillPassport.createRevision.mock.calls[0][1].acknowledged_warnings.sort()).toEqual(["axis_offset_missing", "w_max_missing"]);
    await waitFor(() => expect(onChange).toHaveBeenCalled());
  });

  it("выпуск сначала сохраняет правки формы", async () => {
    const user = userEvent.setup();
    open();
    const horizon = await screen.findByLabelText(/^Горизонт/);
    await waitFor(() => expect(releaseButton()).toHaveProperty("disabled", false));
    await user.clear(horizon);
    await user.type(horizon, "+398");
    await user.click(releaseButton());
    await waitFor(() => expect(api.drillPassport.createRevision).toHaveBeenCalled());
    const save = api.drillPassport.save.mock.invocationCallOrder[0];
    const validate = api.drillPassport.validate.mock.invocationCallOrder.at(-1) ?? 0;
    const release = api.drillPassport.createRevision.mock.invocationCallOrder[0];
    expect(save).toBeLessThan(validate);
    expect(validate).toBeLessThan(release);
    expect(api.drillPassport.save.mock.calls[0][1].payload.horizon).toBe("+398");
    expect(api.drillPassport.createRevision.mock.calls[0][1].expected_version).toBe(4);
  });

  it("409 с новыми предупреждениями — проверка перечитана, сообщение", async () => {
    const user = userEvent.setup();
    open();
    await waitFor(() => expect(releaseButton()).toHaveProperty("disabled", false));
    api.drillPassport.createRevision.mockRejectedValue(Object.assign(new Error("Отметьте предупреждения"), { status: 409 }));
    api.drillPassport.validate.mockResolvedValue(validation66([warning("bit_diameter_missing")]));
    await user.click(releaseButton());
    expect(await screen.findByText(/Отметьте просмотренными новые предупреждения/)).toBeTruthy();
    expect(screen.getAllByRole("checkbox", { name: "просмотрено" })).toHaveLength(1);
  });

  it("ошибка проверки блокирует выпуск и видна", async () => {
    const error: DrillPassportIssue = { level: "error", code: "slope_angles_required", message: "Нужны угол откоса α и γ.", path: "alpha_deg" };
    api.drillPassport.validate.mockResolvedValue(validation66([error]));
    open();
    expect((await screen.findAllByText("Нужны угол откоса α и γ.")).length).toBeGreaterThan(0);
    expect(releaseButton()).toHaveProperty("disabled", true);
  });

  it("несохранённый проект блока — выпуск недоступен", async () => {
    open({ designSaved: false });
    expect(await screen.findByText(/сохраните правки/)).toBeTruthy();
    await waitFor(() => expect(api.drillPassport.validate).toHaveBeenCalled());
    expect(releaseButton()).toHaveProperty("disabled", true);
  });

  it("предпросмотр — PDF в рамке, ошибка — текстом без рамки", async () => {
    const user = userEvent.setup();
    open();
    await user.click(await screen.findByRole("button", { name: "Показать предпросмотр" }));
    expect(fetchBlob).toHaveBeenCalledWith("/preview/p1.pdf");
    expect(await screen.findByTitle("Предпросмотр паспорта")).toBeTruthy();

    fetchBlob.mockRejectedValue(new Error("Предпросмотр недоступен: нет γ."));
    await user.click(screen.getByRole("button", { name: "Показать предпросмотр" }));
    expect(await screen.findByText("Предпросмотр недоступен: нет γ.")).toBeTruthy();
    expect(screen.queryByTitle("Предпросмотр паспорта")).toBeNull();
  });

  it("предпросмотр с правками сохраняет их и перечитывает проверку", async () => {
    const user = userEvent.setup();
    open();
    const horizon = await screen.findByLabelText(/^Горизонт/);
    await waitFor(() => expect(api.drillPassport.validate).toHaveBeenCalledTimes(1));
    const error: DrillPassportIssue = { level: "error", code: "slope_angles_required", message: "Нужны углы α и γ.", path: "alpha_deg" };
    api.drillPassport.validate.mockResolvedValue(validation66([error]));
    await user.type(horizon, "1");
    await user.click(screen.getByRole("button", { name: "Показать предпросмотр" }));
    await waitFor(() => expect(api.drillPassport.save).toHaveBeenCalled());
    expect((await screen.findAllByText("Нужны углы α и γ.")).length).toBeGreaterThan(0);
    expect(releaseButton()).toHaveProperty("disabled", true);
  });

  it("конфликт версии — паспорт можно загрузить заново", async () => {
    const user = userEvent.setup();
    open();
    const horizon = await screen.findByLabelText(/^Горизонт/);
    await user.type(horizon, "1");
    api.drillPassport.save.mockRejectedValue(
      Object.assign(new Error("Паспорт изменён другим пользователем. Обновите данные перед выпуском ревизии."), { status: 409 }),
    );
    api.drillPassport.get.mockResolvedValue({ ...passport66(), version: 7, payload: { ...passport66().payload, horizon: "+398" } });
    await user.click(screen.getByRole("button", { name: "Сохранить" }));
    await user.click(await screen.findByRole("button", { name: "Загрузить сохранённый паспорт" }));
    await waitFor(() => expect((screen.getByLabelText(/^Горизонт/) as HTMLInputElement).value).toBe("+398"));
    api.drillPassport.save.mockResolvedValue({ ...passport66(), version: 8 });
    await user.type(screen.getByLabelText(/^Горизонт/), "2");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));
    await waitFor(() => expect(api.drillPassport.save).toHaveBeenLastCalledWith("p1", expect.objectContaining({ expected_version: 7 })));
  });

  it("409 без новых предупреждений — понятный текст без служебных кодов", async () => {
    const user = userEvent.setup();
    open();
    await waitFor(() => expect(releaseButton()).toHaveProperty("disabled", false));
    api.drillPassport.createRevision.mockRejectedValue(
      Object.assign(new Error("Отметьте предупреждения проверки как просмотренные: bit_diameter_missing"), { status: 409 }),
    );
    await user.click(releaseButton());
    expect(await screen.findByRole("button", { name: "Загрузить сохранённый паспорт" })).toBeTruthy();
    expect(document.body.textContent).not.toContain("bit_diameter_missing");
  });

  it("Esc при несохранённых правках спрашивает", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<DrillPassportDialog passport={passport66()} designSaved onClose={onClose} onChange={vi.fn()} />);
    await user.type(await screen.findByLabelText(/^Горизонт/), "1");
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const dialog = screen.getByRole("dialog", { name: /Паспорт на бурение №/ });
    const cancel = new Event("cancel", { cancelable: true });
    fireEvent(dialog, cancel);
    expect(confirm).toHaveBeenCalled();
    expect(cancel.defaultPrevented).toBe(true);
    confirm.mockRestore();
  });

  it("пока идёт сохранение, подписи и ознакомление не редактируются", async () => {
    const user = userEvent.setup();
    open();
    const horizon = await screen.findByLabelText(/^Горизонт/);
    await waitFor(() => expect(releaseButton()).toHaveProperty("disabled", false));
    await user.type(horizon, "1");
    api.drillPassport.save.mockReturnValue(new Promise(() => undefined));
    await user.click(releaseButton());
    // Поле в отключённом fieldset недоступно, хотя его свойство disabled — false.
    await waitFor(() => expect(screen.getByLabelText("СОГЛАСОВАНО: ФИО").matches(":disabled")).toBe(true));
    expect(screen.getByRole("button", { name: "Добавить человека" }).matches(":disabled")).toBe(true);
  });

  it("изменился текст отмеченного предупреждения — выпуск останавливается", async () => {
    const before = { ...warning("first_row_burden", "w_max_m"), message: "W 7,2 м больше 7,0 м" };
    api.drillPassport.validate.mockResolvedValue(validation66([before]));
    const user = userEvent.setup();
    open();
    await user.click(await screen.findByRole("checkbox", { name: "просмотрено" }));
    await user.type(screen.getByLabelText(/Допустимая ЛСПП Wпред/), "5");
    api.drillPassport.validate.mockResolvedValue(validation66([{ ...before, message: "W 7,2 м больше 5,0 м" }]));
    await user.click(releaseButton());
    expect(await screen.findByText(/Отметьте просмотренными новые предупреждения/)).toBeTruthy();
    expect(api.drillPassport.createRevision).not.toHaveBeenCalled();
    expect(screen.getByRole("checkbox", { name: "просмотрено" })).toHaveProperty("checked", false);
  });

  it("с ошибкой проверки предпросмотр недоступен", async () => {
    const error: DrillPassportIssue = { level: "error", code: "slope_angles_required", message: "Нужны углы.", path: "alpha_deg" };
    api.drillPassport.validate.mockResolvedValue(validation66([error]));
    open();
    await screen.findAllByText("Нужны углы.");
    expect(screen.getByRole("button", { name: "Показать предпросмотр" })).toHaveProperty("disabled", true);
  });

  it("в списках справочников — названия без служебных кодов", async () => {
    open();
    await waitFor(() => expect(screen.getByLabelText(/^Объект$/).tagName).toBe("SELECT"));
    const options = within(screen.getByLabelText(/^Объект$/)).getAllByRole("option").map((option) => option.textContent);
    expect(options).toEqual(["— не выбран —", "Жуков Камень"]);
  });

  it("одинаковые названия различаются кодом", async () => {
    api.economics.referenceSnapshot.mockResolvedValue({
      ...SNAPSHOT,
      sections: { ...SNAPSHOT.sections, sites: [...SNAPSHOT.sections.sites, { code: "ZHK2", name: "Жуков Камень", payload: {}, is_active: true }] },
    });
    open();
    await waitFor(() => expect(screen.getByLabelText(/^Объект$/).tagName).toBe("SELECT"));
    const options = within(screen.getByLabelText(/^Объект$/)).getAllByRole("option").map((option) => option.textContent);
    expect(options).toEqual(["— не выбран —", "Жуков Камень (ZHK)", "Жуков Камень (ZHK2)"]);
  });

  it("исправление в форме открывает предпросмотр и выпуск до сохранения", async () => {
    const error: DrillPassportIssue = { level: "error", code: "slope_angles_required", message: "Нужны углы.", path: "alpha_deg" };
    api.drillPassport.validate.mockResolvedValue(validation66([error]));
    const user = userEvent.setup();
    open();
    await screen.findAllByText("Нужны углы.");
    expect(screen.getByRole("button", { name: "Показать предпросмотр" })).toHaveProperty("disabled", true);
    await user.type(screen.getByLabelText(/Угол откоса рабочего уступа α/), "75");
    expect(screen.getByRole("button", { name: "Показать предпросмотр" })).toHaveProperty("disabled", false);
    expect(releaseButton()).toHaveProperty("disabled", false);
    expect(screen.queryByText(/Предпросмотр — после исправления ошибок/)).toBeNull();
  });

  it("409 «только из черновика» — паспорт перечитан, понятный текст", async () => {
    const user = userEvent.setup();
    open();
    await waitFor(() => expect(releaseButton()).toHaveProperty("disabled", false));
    api.drillPassport.createRevision.mockRejectedValue(
      Object.assign(new Error("Ревизию можно выпустить только из черновика."), { status: 409 }),
    );
    api.drillPassport.get.mockResolvedValue({ ...passport66(), status: "approved", version: 9 });
    await user.click(releaseButton());
    expect(await screen.findByText(/Паспорт уже не черновик/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Загрузить сохранённый паспорт" })).toBeNull();
    expect(screen.queryByText(/изменён в другом окне/)).toBeNull();
  });

  it("Esc (keydown) при правках — свой вопрос, отказ оставляет окно", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<DrillPassportDialog passport={passport66()} designSaved onClose={onClose} onChange={vi.fn()} />);
    await user.type(await screen.findByLabelText(/^Горизонт/), "1");
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const dialog = screen.getByRole("dialog", { name: /Паспорт на бурение №/ });
    const first = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });
    fireEvent(dialog, first);
    expect(first.defaultPrevented).toBe(true);
    const second = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });
    fireEvent(dialog, second);
    expect(second.defaultPrevented).toBe(true);
    expect(confirm).toHaveBeenCalledTimes(2);
    expect(onClose).not.toHaveBeenCalled();
    confirm.mockReturnValue(true);
    fireEvent(dialog, new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
    expect(onClose).toHaveBeenCalled();
    confirm.mockRestore();
  });

  it("Esc в справке закрывает только справку", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<DrillPassportDialog passport={passport66()} designSaved onClose={onClose} onChange={vi.fn()} />);
    await user.type(await screen.findByLabelText(/^Горизонт/), "1");
    await user.click(screen.getByRole("button", { name: "Справка по паспорту на бурение" }));
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const help = screen.getByRole("dialog", { name: "Паспорт на бурение: справка" });
    const esc = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });
    fireEvent(help, esc);
    expect(confirm).not.toHaveBeenCalled();
    expect(esc.defaultPrevented).toBe(false);
    expect(onClose).not.toHaveBeenCalled();
    confirm.mockRestore();
  });

  it("после сохранения старый предпросмотр убирается", async () => {
    const user = userEvent.setup();
    open();
    await user.click(await screen.findByRole("button", { name: "Показать предпросмотр" }));
    expect(await screen.findByTitle("Предпросмотр паспорта")).toBeTruthy();
    await user.type(screen.getByLabelText(/Угол устойчивого борта γ/), "60");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));
    await waitFor(() => expect(screen.queryByTitle("Предпросмотр паспорта")).toBeNull());
    expect(screen.getByText(/Паспорт изменён — покажите предпросмотр заново/)).toBeTruthy();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:preview");
  });

  it("после загрузки сохранённого паспорта старый предпросмотр убирается", async () => {
    const user = userEvent.setup();
    open();
    await user.click(await screen.findByRole("button", { name: "Показать предпросмотр" }));
    expect(await screen.findByTitle("Предпросмотр паспорта")).toBeTruthy();
    await user.type(screen.getByLabelText(/^Горизонт/), "1");
    api.drillPassport.save.mockRejectedValue(Object.assign(new Error("Паспорт изменён другим пользователем."), { status: 409 }));
    await user.click(screen.getByRole("button", { name: "Сохранить" }));
    await user.click(await screen.findByRole("button", { name: "Загрузить сохранённый паспорт" }));
    await waitFor(() => expect(screen.queryByTitle("Предпросмотр паспорта")).toBeNull());
  });

  it("выбор объекта с профилем подставляет профиль и его порядок работ", async () => {
    api.economics.referenceSnapshot.mockResolvedValue({
      ...SNAPSHOT,
      sections: {
        ...SNAPSHOT.sections,
        sites: [
          ...SNAPSHOT.sections.sites,
          { code: "KGOK_SITE", name: "Гусевогорское", payload: { drill_passport_profile_code: "KGOK" }, is_active: true },
        ],
        drill_passport_profiles: [
          { code: "KGOK", name: "Профиль КГОК", payload: { power_lines: "ВЛ 6 кВ — по наряду-допуску", stakeout: "" }, is_active: true },
        ],
      },
    });
    const user = userEvent.setup();
    open();
    await waitFor(() => expect(screen.getByLabelText(/^Объект$/).tagName).toBe("SELECT"));
    const stakeoutBefore = (screen.getByLabelText(/^Вынос точек/) as HTMLTextAreaElement).value;
    await user.selectOptions(screen.getByLabelText(/^Объект$/), "KGOK_SITE");
    expect((screen.getByLabelText(/^Профиль паспорта/) as HTMLSelectElement).value).toBe("KGOK");
    expect((screen.getByLabelText(/^ЛЭП и кабели/) as HTMLTextAreaElement).value).toBe("ВЛ 6 кВ — по наряду-допуску");
    // Пустое поле профиля прежний текст не стирает.
    expect((screen.getByLabelText(/^Вынос точек/) as HTMLTextAreaElement).value).toBe(stakeoutBefore);
  });

  it("объект без профиля сбрасывает профиль прежнего объекта", async () => {
    api.economics.referenceSnapshot.mockResolvedValue({
      ...SNAPSHOT,
      sections: {
        ...SNAPSHOT.sections,
        sites: [
          { code: "ZHK", name: "Жуков Камень", payload: { drill_passport_profile_code: "KGOK" }, is_active: true },
          { code: "PLAIN", name: "Без профиля", payload: {}, is_active: true },
        ],
      },
    });
    const user = userEvent.setup();
    render(
      <DrillPassportDialog
        passport={{ ...passport66(), payload: { ...passport66().payload, profile_code: "KGOK" } }}
        designSaved onClose={vi.fn()} onChange={vi.fn()}
      />,
    );
    await waitFor(() => expect(screen.getByLabelText(/^Объект$/).tagName).toBe("SELECT"));
    await user.selectOptions(screen.getByLabelText(/^Объект$/), "PLAIN");
    expect((screen.getByLabelText(/^Профиль паспорта/) as HTMLSelectElement).value).toBe("");
  });

  it("проверка первого ряда со статусами, без JSON", async () => {
    const { container } = render(
      <DrillPassportDialog passport={passport66()} designSaved onClose={vi.fn()} onChange={vi.fn()} />,
    );
    const check = await screen.findByRole("table", { name: "Проверка первого ряда" });
    await waitFor(() => expect(within(check).getByText("2,0 м")).toBeTruthy());
    expect(within(check).getByText("Безопасное расстояние s")).toBeTruthy();
    expect(container.textContent).not.toContain('{"');
  });
});
