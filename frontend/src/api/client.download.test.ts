// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { downloadFile, fetchBlob } from "./client";
import { api } from "./endpoints";

const fetchMock = vi.fn();
const clicked: string[] = [];

beforeEach(() => {
  fetchMock.mockReset();
  clicked.length = 0;
  vi.stubGlobal("fetch", fetchMock);
  URL.createObjectURL = vi.fn(() => "blob:test");
  URL.revokeObjectURL = vi.fn();
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
    clicked.push(this.download);
  });
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const file = (headers: Record<string, string>) => new Response("data", { status: 200, headers });

describe("downloadFile", () => {
  it("имя файла — из filename* в UTF-8", async () => {
    fetchMock.mockResolvedValue(
      file({
        "Content-Disposition":
          "attachment; filename*=UTF-8''%D0%A1%D0%BA%D0%B2%D0%B0%D0%B6%D0%B8%D0%BD%D1%8B%2066-26-%D0%91%20rev1.dxf",
      }),
    );
    const result = await downloadFile("/api/v1/x/holes.dxf", "holes.dxf");
    expect(result).toEqual({ filename: "Скважины 66-26-Б rev1.dxf", warning: null });
    expect(clicked).toEqual(["Скважины 66-26-Б rev1.dxf"]);
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ credentials: "include" });
  });

  it("предупреждение сервера раскодировано", async () => {
    fetchMock.mockResolvedValue(
      file({
        "Content-Disposition": 'attachment; filename="holes.dxf"',
        "X-BlastEX-Warning": encodeURIComponent("DWG пока не формируется: используйте DXF."),
      }),
    );
    const result = await downloadFile("/api/v1/x/holes.dwg", "holes.dwg");
    expect(result.filename).toBe("holes.dxf");
    expect(result.warning).toBe("DWG пока не формируется: используйте DXF.");
  });

  it("без заголовка имени — запасное", async () => {
    fetchMock.mockResolvedValue(file({}));
    expect((await downloadFile("/x", "Паспорт.pdf")).filename).toBe("Паспорт.pdf");
  });

  it("ошибка — русский текст сервера, файл не сохраняется", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: "Файл выноса не сформируется: длинный блок." }), { status: 422 }),
    );
    await expect(downloadFile("/x", "a.csv")).rejects.toThrow("Файл выноса не сформируется: длинный блок.");
    expect(clicked).toEqual([]);
  });
});

describe("downloadFile: параметры", () => {
  it("заданное имя главнее имени сервера, свой текст ошибки", async () => {
    fetchMock.mockResolvedValue(file({ "Content-Disposition": 'attachment; filename="block-66.csv"' }));
    expect((await downloadFile("/x", "x.csv", { filename: "Блок 66.csv" })).filename).toBe("Блок 66.csv");
    fetchMock.mockResolvedValue(new Response("", { status: 500 }));
    await expect(downloadFile("/x", "x.csv", { errorText: "Не удалось экспортировать паспорт." })).rejects.toThrow(
      "Не удалось экспортировать паспорт.",
    );
  });
});

describe("старые выгрузки — через downloadFile", () => {
  it("экспорт справочников берёт кириллическое имя из filename*", async () => {
    fetchMock.mockResolvedValue(file({ "Content-Disposition": "attachment; filename*=UTF-8''%D0%A1%D0%BF%D1%80%D0%B0%D0%B2%D0%BE%D1%87%D0%BD%D0%B8%D0%BA%D0%B8.xlsx" }));
    await api.economics.exportReferences("xlsx");
    expect(clicked).toEqual(["Справочники.xlsx"]);
  });

  it("CSV паспорта БВР — под заданным именем", async () => {
    fetchMock.mockResolvedValue(file({ "Content-Disposition": 'attachment; filename="block-66.csv"' }));
    await api.design.exportCsv("block-66", "Блок 66.csv");
    expect(clicked).toEqual(["Блок 66.csv"]);
  });
});

describe("fetchBlob", () => {
  it("ошибка 422 — текст сервера", async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: "Предпросмотр недоступен: нет γ." }), { status: 422 }));
    await expect(fetchBlob("/x")).rejects.toThrow("Предпросмотр недоступен: нет γ.");
  });
});

describe("api.drillPassport", () => {
  it("адреса файлов ревизии и профиль файла выноса", () => {
    expect(api.drillPassport.fileUrl("r 1", "holes.dwg")).toBe("/api/v1/design/drilling-passports/revisions/r%201/holes.dwg");
    expect(api.drillPassport.stakeoutUrl("r1", "PENZD_CSV")).toBe(
      "/api/v1/design/drilling-passports/revisions/r1/stakeout?profile=PENZD_CSV",
    );
    expect(api.drillPassport.previewUrl("p1")).toBe("/api/v1/design/drilling-passports/p1/preview.pdf");
  });

  it("список паспортов проекта", async () => {
    fetchMock.mockResolvedValue(new Response("[]", { status: 200 }));
    await api.drillPassport.list("блок 66");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/design/drilling-passports?design_id=%D0%B1%D0%BB%D0%BE%D0%BA%2066");
  });
});
