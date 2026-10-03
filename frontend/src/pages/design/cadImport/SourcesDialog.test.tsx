// @vitest-environment jsdom
// «Чертежи объекта» (TASK-013, PR 4): загруженные файлы объекта — открыть в
// окне импорта без повторной загрузки или удалить насовсем.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import type { CadSiteSources } from "../../../types/cad";
import { SourcesDialog, type SourcesDialogProps } from "./SourcesDialog";
import { cadSource } from "./testing/fixtures";

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

const LIST: CadSiteSources = {
  site_code: "SITE_ZK",
  truncated: false,
  sources: [
    {
      id: "src-9",
      title: "Положение горных работ",
      file_name: "Положение горных работ на 01.09.2026.dxf",
      survey_date: "2026-09-01",
      uploaded_at: "2026-09-02T10:00:00+00:00",
      uploaded_by: "engineer@example.ru",
      situation_count: 120,
    },
    {
      id: "src-1",
      title: "граница блока 66",
      file_name: "28.09.2026г граница блока 66.dwg",
      survey_date: null,
      uploaded_at: "2026-09-30T10:00:00+00:00",
      uploaded_by: "engineer@example.ru",
      situation_count: 0,
    },
  ],
};

function renderDialog(extra: Partial<SourcesDialogProps> = {}) {
  const props: SourcesDialogProps = {
    onClose: vi.fn(),
    onOpenSource: vi.fn(),
    onDeleted: vi.fn(),
    list: vi.fn(async () => LIST),
    load: vi.fn(async (id: string) => cadSource({ id })),
    remove: vi.fn(async () => undefined),
    ...extra,
  };
  render(<SourcesDialog {...props} />);
  return props;
}

describe("SourcesDialog", () => {
  it("список: название, дата съёмки, файл, кто и когда, объекты ситуации", async () => {
    renderDialog();
    const row = (await screen.findByText("Положение горных работ")).closest("tr") as HTMLElement;

    expect(within(row).getByText("01.09.2026")).toBeTruthy();
    expect(within(row).getByText(/Положение горных работ на 01\.09\.2026\.dxf/)).toBeTruthy();
    expect(within(row).getByText(/02\.09\.2026 · engineer@example\.ru/)).toBeTruthy();
    expect(within(row).getByText("120")).toBeTruthy();
  });

  it("«Открыть» загружает разбор и отдаёт его странице", async () => {
    const props = renderDialog();
    const row = (await screen.findByText("граница блока 66")).closest("tr") as HTMLElement;

    fireEvent.click(within(row).getByRole("button", { name: "Открыть" }));

    await waitFor(() => expect(props.onOpenSource).toHaveBeenCalledWith(expect.objectContaining({ id: "src-1" })));
    expect(props.load).toHaveBeenCalledWith("src-1");
  });

  it("«Удалить» — только после подтверждения, строка уходит", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    const props = renderDialog();
    const row = (await screen.findByText("Положение горных работ")).closest("tr") as HTMLElement;

    fireEvent.click(within(row).getByRole("button", { name: "Удалить" }));
    expect(props.remove).not.toHaveBeenCalled();
    expect(confirm.mock.calls[0][0]).toMatch(/сохранят контур и кровлю/);

    fireEvent.click(within(row).getByRole("button", { name: "Удалить" }));
    await waitFor(() => expect(props.remove).toHaveBeenCalledWith("src-9"));
    await waitFor(() => expect(screen.queryByText("Положение горных работ")).toBeNull());
    expect(props.onDeleted).toHaveBeenCalledWith("src-9");
  });

  it("ошибка удаления видна, строка остаётся", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderDialog({ remove: vi.fn(async () => Promise.reject(new Error("Импорт чертежа не найден."))) });
    const row = (await screen.findByText("Положение горных работ")).closest("tr") as HTMLElement;

    fireEvent.click(within(row).getByRole("button", { name: "Удалить" }));

    expect((await screen.findByRole("alert")).textContent).toBe("Импорт чертежа не найден.");
    expect(screen.getByText("Положение горных работ")).toBeTruthy();
  });

  it("без объекта работ — объяснение вместо списка", async () => {
    renderDialog({ list: vi.fn(async () => ({ site_code: "", sources: [], truncated: false })) });

    expect(await screen.findByText(/Объект работ не выбран/)).toBeTruthy();
  });

  it("пустой список объекта", async () => {
    renderDialog({ list: vi.fn(async () => ({ site_code: "SITE_ZK", sources: [], truncated: false })) });

    expect(await screen.findByText("Чертежей объекта ещё нет.")).toBeTruthy();
  });
});
