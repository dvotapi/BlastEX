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

    await api.cad.upload([first, second], { workObjectName: "Жуков камень", benchHeightM: 12, floorZM: null });

    const [path, init] = fetchMock.mock.calls.at(-1) as [string, RequestInit];
    expect(path).toBe("/api/v1/design/cad/sources");
    expect(init.method).toBe("POST");
    const form = init.body as FormData;
    expect(form.getAll("files").map((file) => (file as File).name)).toEqual(["блок 66.dwg", "ситуация.dxf"]);
    expect(form.get("work_object_name")).toBe("Жуков камень");
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

    await expect(api.cad.upload([new File(["x"], "битый.dxf")], { workObjectName: "" })).rejects.toThrow(
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
