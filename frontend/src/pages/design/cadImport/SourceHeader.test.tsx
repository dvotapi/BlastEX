// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CadCrsResponse, CadSourceMetaResponse } from "../../../types/cad";
import { SourceHeader, type SourceHeaderProps } from "./SourceHeader";
import { cadSource } from "./testing/fixtures";

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

const MSK66 = { name: "МСК-66 зона 1", height_system: "Балтийская 1977", epsg: null };

function metaAnswer(extra: Partial<CadSourceMetaResponse> = {}): CadSourceMetaResponse {
  return { id: "src-1", title: "блок 66", survey_date: null, series: [], ...extra };
}

function renderHeader(extra: Partial<SourceHeaderProps> = {}) {
  const props: SourceHeaderProps = {
    source: cadSource(),
    knownTitles: ["Положение горных работ"],
    disabled: false,
    saveMeta: vi.fn(async (_id, payload) => metaAnswer({ title: payload.title ?? "блок 66", survey_date: payload.survey_date ?? null })),
    saveCrs: vi.fn(async (_id, crs): Promise<CadCrsResponse> => ({ crs, saved: true, warnings: [] })),
    onMetaSaved: vi.fn(),
    onCrsSaved: vi.fn(),
    ...extra,
  };
  const view = render(<SourceHeader {...props} />);
  return { props, view };
}

async function flush() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(450);
  });
}

describe("SourceHeader", () => {
  it("показывает название, дату и прежние версии серии", () => {
    renderHeader({
      source: cadSource({
        title: "Положение горных работ",
        survey_date: "2026-10-01",
        series: [
          { id: "old", title: "Положение горных работ", file_name: "п.dxf", survey_date: "2026-09-01", uploaded_at: "2026-09-02T10:00:00+00:00" },
        ],
      }),
    });

    expect((screen.getByLabelText("Название") as HTMLInputElement).value).toBe("Положение горных работ");
    expect((screen.getByLabelText("Дата съёмки") as HTMLInputElement).value).toBe("2026-10-01");
    expect(screen.getByText(/Другие версии серии: 01\.09\.2026/)).toBeTruthy();
  });

  it("название сохраняется одним запросом после паузы", async () => {
    const { props } = renderHeader();
    const input = screen.getByLabelText("Название");

    fireEvent.change(input, { target: { value: "Положение" } });
    fireEvent.change(input, { target: { value: "Положение горных работ" } });
    await flush();

    expect(props.saveMeta).toHaveBeenCalledTimes(1);
    expect(props.saveMeta).toHaveBeenCalledWith("src-1", { title: "Положение горных работ" });
    expect(props.onMetaSaved).toHaveBeenCalledWith(expect.objectContaining({ title: "Положение горных работ" }));
  });

  it("пустое название не отправляется", async () => {
    const { props } = renderHeader();

    fireEvent.change(screen.getByLabelText("Название"), { target: { value: "  " } });
    await flush();

    expect(props.saveMeta).not.toHaveBeenCalled();
    expect(screen.getByRole("alert").textContent).toMatch(/Название не может быть пустым/);
  });

  it("дата съёмки сохраняется и стирается", async () => {
    const { props } = renderHeader();
    const input = screen.getByLabelText("Дата съёмки");

    fireEvent.change(input, { target: { value: "2026-10-01" } });
    await flush();
    expect(props.saveMeta).toHaveBeenLastCalledWith("src-1", { survey_date: "2026-10-01" });

    fireEvent.change(input, { target: { value: "" } });
    await flush();
    expect(props.saveMeta).toHaveBeenLastCalledWith("src-1", { survey_date: null });
  });

  it("устаревший ответ не применяется", async () => {
    let releaseFirst: (value: CadSourceMetaResponse) => void = () => undefined;
    const saveMeta = vi
      .fn()
      .mockImplementationOnce(() => new Promise<CadSourceMetaResponse>((resolve) => (releaseFirst = resolve)))
      .mockImplementationOnce(async () => metaAnswer({ title: "второе" }));
    const { props } = renderHeader({ saveMeta });
    const input = screen.getByLabelText("Название");

    fireEvent.change(input, { target: { value: "первое" } });
    await flush();
    fireEvent.change(input, { target: { value: "второе" } });
    await flush();
    await act(async () => releaseFirst(metaAnswer({ title: "первое" })));

    expect(props.onMetaSaved).toHaveBeenCalledTimes(1);
    expect(props.onMetaSaved).toHaveBeenCalledWith(expect.objectContaining({ title: "второе" }));
  });

  it("ошибка сохранения видна у полей", async () => {
    renderHeader({ saveMeta: vi.fn(async () => Promise.reject(new Error("Источник правят в другом окне."))) });

    fireEvent.change(screen.getByLabelText("Название"), { target: { value: "x" } });
    await flush();

    expect(screen.getByRole("alert").textContent).toBe("Источник правят в другом окне.");
  });

  it("СК объекта задаётся один раз: «Изменить» → поля → «Сохранить»", async () => {
    const { props } = renderHeader();
    expect(screen.getByText(/СК объекта/).textContent).toMatch(/не задана/);

    fireEvent.click(screen.getByRole("button", { name: "Изменить" }));
    fireEvent.change(screen.getByLabelText("Система координат"), { target: { value: "МСК-66 зона 1" } });
    fireEvent.change(screen.getByLabelText("Система высот"), { target: { value: "Балтийская 1977" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));
    });

    expect(props.saveCrs).toHaveBeenCalledWith("src-1", MSK66);
    expect(props.onCrsSaved).toHaveBeenCalledWith("src-1", { crs: MSK66, saved: true, warnings: [] });
    expect(screen.queryByLabelText("Система координат")).toBeNull();
  });

  it("СК без названия или с неверным EPSG не сохраняется", async () => {
    const { props } = renderHeader();
    fireEvent.click(screen.getByRole("button", { name: "Изменить" }));

    fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));
    expect(screen.getByRole("alert").textContent).toMatch(/Укажите систему координат/);

    fireEvent.change(screen.getByLabelText("Система координат"), { target: { value: "МСК-66 зона 1" } });
    fireEvent.change(screen.getByLabelText("EPSG"), { target: { value: "-3" } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));
    expect(screen.getByRole("alert").textContent).toMatch(/EPSG/);
    expect(props.saveCrs).not.toHaveBeenCalled();
  });

  it("заданная СК показана одной строкой", () => {
    renderHeader({ source: cadSource({ crs: { ...MSK66, epsg: null } }) });
    expect(screen.getByText(/СК объекта/).textContent).toMatch(/МСК-66 зона 1 · высоты Балтийская 1977/);
  });

  it("без объекта работ СК хранить негде", () => {
    renderHeader({ source: cadSource({ site_code: "", template_saved: false }) });

    expect(screen.getByText(/СК объекта/).textContent).toMatch(/объект работ не выбран/);
    expect(screen.queryByRole("button", { name: "Изменить" })).toBeNull();
  });

  it("другой файл — свои поля", () => {
    const { view, props } = renderHeader();
    fireEvent.change(screen.getByLabelText("Название"), { target: { value: "черновик" } });

    view.rerender(<SourceHeader {...props} source={cadSource({ id: "src-2", title: "другой" })} />);

    expect((screen.getByLabelText("Название") as HTMLInputElement).value).toBe("другой");
  });

  it("версии одной даты в серии различаются временем загрузки", () => {
    const version = (id: string, uploaded_at: string) => ({
      id,
      title: "Положение горных работ",
      file_name: "п.dxf",
      survey_date: "2026-09-01",
      uploaded_at,
    });
    renderHeader({
      source: cadSource({ series: [version("b", "2026-10-03T03:31:14+00:00"), version("a", "2026-10-02T18:05:00+00:00")] }),
    });

    expect(
      screen.getByText("Другие версии серии: 01.09.2026 · загружен 03.10.2026 03:31, 01.09.2026 · загружен 02.10.2026 18:05"),
    ).toBeTruthy();
  });
});
