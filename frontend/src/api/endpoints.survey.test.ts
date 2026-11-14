import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "./endpoints";

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  fetchMock.mockImplementation(
    async () => new Response('{"points": []}', { status: 200, headers: { "Content-Type": "application/json" } }),
  );
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

describe("api.survey: съёмка к проекту", () => {
  it("read шлёт файл и заданные параметры одной формой, колонки — JSON-строкой", async () => {
    const file = new File(["1-01,2,8,0"], "съёмка 66.csv");

    await api.survey.read(file, { format: "TABLE", swapXy: false, columns: { north: "X", east: "Y" } });

    const [path, init] = fetchMock.mock.calls.at(-1) as [string, RequestInit];
    expect(path).toBe("/api/v1/design/survey/read");
    expect(init.method).toBe("POST");
    const form = init.body as FormData;
    expect((form.get("file") as File).name).toBe("съёмка 66.csv");
    expect(form.get("format")).toBe("TABLE");
    expect(form.get("swap_xy")).toBe("false");
    expect(JSON.parse(String(form.get("columns")))).toEqual({ north: "X", east: "Y" });
  });

  it("read без параметров: формат и колонки определяет сервер", async () => {
    await api.survey.read(new File(["x"], "s.csv"));

    const form = (fetchMock.mock.calls.at(-1) as [string, RequestInit])[1].body as FormData;
    expect(form.has("format")).toBe(false);
    expect(form.has("swap_xy")).toBe(false);
    expect(form.has("columns")).toBe(false);
  });
});
