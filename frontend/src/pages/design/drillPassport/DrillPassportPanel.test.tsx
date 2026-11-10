// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { passport66, validation66 } from "./testFixtures";

const api = vi.hoisted(() => ({
  drillPassport: {
    list: vi.fn(),
    create: vi.fn(),
    revision: vi.fn(),
    validate: vi.fn(),
    get: vi.fn(),
    previewUrl: (id: string) => `/preview/${id}.pdf`,
  },
  economics: { referenceSnapshot: vi.fn() },
}));
vi.mock("../../../api/endpoints", () => ({ api }));

import { DrillPassportPanel } from "./DrillPassportPanel";

beforeAll(() => {
  HTMLDialogElement.prototype.showModal = vi.fn(function (this: HTMLDialogElement) {
    this.open = true;
  });
  HTMLDialogElement.prototype.close = vi.fn(function (this: HTMLDialogElement) {
    this.open = false;
  });
});
beforeEach(() => {
  api.drillPassport.list.mockReset().mockResolvedValue([]);
  api.drillPassport.create.mockReset().mockResolvedValue(passport66());
  api.drillPassport.revision.mockReset().mockResolvedValue({
    id: "rev-1", passport_id: "p1", revision_no: 2, content_sha256: "", created_at: "", created_by: "", context: {},
  });
  api.drillPassport.validate.mockReset().mockResolvedValue(validation66());
  api.economics.referenceSnapshot.mockReset().mockRejectedValue(new Error("нет"));
});
afterEach(cleanup);

describe("DrillPassportPanel", () => {
  it("без сохранённого проекта — подсказка, паспорт не ищется", () => {
    render(<DrillPassportPanel designId="" designSaved />);
    expect(screen.getByText(/Сначала сохраните проект блока/)).toBeTruthy();
    expect(api.drillPassport.list).not.toHaveBeenCalled();
  });

  it("паспорта нет — «Создать паспорт» создаёт и открывает окно", async () => {
    const user = userEvent.setup();
    render(<DrillPassportPanel designId="block-66" designSaved />);
    await user.click(await screen.findByRole("button", { name: "Создать паспорт" }));
    expect(api.drillPassport.create).toHaveBeenCalledWith({ design_id: "block-66" });
    expect(await screen.findByRole("dialog", { name: /Паспорт на бурение № 66-26\/Б/ })).toBeTruthy();
  });

  it("берётся последний изменённый паспорт проекта", async () => {
    api.drillPassport.list.mockResolvedValue([
      { ...passport66(), id: "p2", passport_no: "66-26/Б-2" },
      passport66(),
    ]);
    render(<DrillPassportPanel designId="block-66" designSaved />);
    expect(await screen.findByText(/№ 66-26\/Б-2/)).toBeTruthy();
    expect(screen.getByText(/Ревизия не выпущена/)).toBeTruthy();
  });

  it("выпущенная ревизия — номер и кнопки документов", async () => {
    api.drillPassport.list.mockResolvedValue([{ ...passport66(), current_revision_id: "rev-1" }]);
    render(<DrillPassportPanel designId="block-66" designSaved />);
    expect(await screen.findByText(/Ревизия № 2/)).toBeTruthy();
    await waitFor(() => expect(api.drillPassport.revision).toHaveBeenCalledWith("rev-1"));
    expect(screen.getByRole("button", { name: "Паспорт PDF" })).toBeTruthy();
  });

  it("закрытие окна перечитывает паспорт (версия после выпуска)", async () => {
    api.drillPassport.list.mockResolvedValue([passport66()]);
    const user = userEvent.setup();
    render(<DrillPassportPanel designId="block-66" designSaved />);
    await user.click(await screen.findByRole("button", { name: "Открыть паспорт" }));
    await user.click(await screen.findByRole("button", { name: "Закрыть" }));
    await waitFor(() => expect(api.drillPassport.list).toHaveBeenCalledTimes(2));
  });

  it("несохранённый проект блока — предупреждение", async () => {
    api.drillPassport.list.mockResolvedValue([passport66()]);
    render(<DrillPassportPanel designId="block-66" designSaved={false} />);
    expect(await screen.findByText(/по сохранённому проекту/)).toBeTruthy();
  });

  it("ошибка загрузки — текст, не пустая панель", async () => {
    api.drillPassport.list.mockRejectedValue(new Error("Паспорта на бурение временно недоступны."));
    render(<DrillPassportPanel designId="block-66" designSaved />);
    expect(await screen.findByText("Паспорта на бурение временно недоступны.")).toBeTruthy();
  });
});
