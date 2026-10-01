import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "./endpoints";

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  fetchMock.mockImplementation(
    async () => new Response('{"sources": []}', { status: 201, headers: { "Content-Type": "application/json" } }),
  );
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

describe("api.cad: импорт чертежа", () => {
  it("upload шлёт все файлы и параметры одной формой", async () => {
    const first = new File(["a"], "блок 66.dwg");
    const second = new File(["b"], "ситуация.dxf");

    await api.cad.upload([first, second], { benchHeightM: 12, floorZM: null });

    const [path, init] = fetchMock.mock.calls.at(-1) as [string, RequestInit];
    expect(path).toBe("/api/v1/design/cad/sources");
    expect(init.method).toBe("POST");
    const form = init.body as FormData;
    expect(form.getAll("files").map((file) => (file as File).name)).toEqual(["блок 66.dwg", "ситуация.dxf"]);
    // Объект работ берёт сервер (активный объект организации), клиент его не шлёт.
    expect(form.has("work_object_name")).toBe(false);
    expect(form.get("bench_height_m")).toBe("12");
    // Пустая подошва не отправляется: сервер ищет её в имени слоя.
    expect(form.has("floor_z_m")).toBe(false);
  });

  it("ошибка сервера доходит текстом из detail", async () => {
    fetchMock.mockImplementation(
      async () =>
        new Response(JSON.stringify({ detail: "«битый.dxf»: Не удалось прочитать DXF." }), {
          status: 422,
          headers: { "Content-Type": "application/json" },
        }),
    );

    await expect(api.cad.upload([new File(["x"], "битый.dxf")], {})).rejects.toThrow(
      "«битый.dxf»: Не удалось прочитать DXF.",
    );
  });

  it("saveRoles и reparse идут по пути источника", async () => {
    await api.cad.saveRoles("src/1", { layers: { Отвал: "ignore" } });
    let [path, init] = fetchMock.mock.calls.at(-1) as [string, RequestInit];
    expect(path).toBe("/api/v1/design/cad/sources/src%2F1/roles");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(String(init.body))).toEqual({ layers: { Отвал: "ignore" } });

    await api.cad.reparse("src/1", { scale: 0.001, label_radius_m: 3, floor_z_m: null, bench_height_m: 10 });
    [path, init] = fetchMock.mock.calls.at(-1) as [string, RequestInit];
    expect(path).toBe("/api/v1/design/cad/sources/src%2F1/reparse");
    expect(JSON.parse(String(init.body)).scale).toBe(0.001);
  });
});

describe("api.cad: контур блока (PR 2)", () => {
  it("линии для контура и предпросмотр — POST на источник", async () => {
    fetchMock.mockImplementation(async () => new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } }));

    await api.cad.contourLines("src 1", ["block_contour", "crest_top"]);
    let [path, init] = fetchMock.mock.calls.at(-1) as [string, RequestInit];
    expect(path).toBe("/api/v1/design/cad/sources/src%201/contour/lines");
    expect(JSON.parse(init.body as string)).toEqual({ roles: ["block_contour", "crest_top"] });

    await api.cad.contour("src 1", { method: "ready", handle: "769", tolerance_m: 0.5 });
    [path, init] = fetchMock.mock.calls.at(-1) as [string, RequestInit];
    expect(path).toBe("/api/v1/design/cad/sources/src%201/contour");
    expect(JSON.parse(init.body as string)).toMatchObject({ method: "ready", handle: "769" });
  });

  it("площадь блока сохраняется на объекте — PUT на источник", async () => {
    fetchMock.mockImplementation(async () => new Response('{"area_basis":"top","saved":true}', { status: 200, headers: { "Content-Type": "application/json" } }));

    await api.cad.saveAreaBasis("src 1", "top");

    const [path, init] = fetchMock.mock.calls.at(-1) as [string, RequestInit];
    expect(path).toBe("/api/v1/design/cad/sources/src%201/area-basis");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body as string)).toEqual({ area_basis: "top" });
  });

  it("построения «полосой между бровками» в клиенте больше нет", () => {
    expect("benchFromPolylines" in api.design).toBe(false);
    expect("importBenchDxf" in api.design).toBe(false);
  });
});
