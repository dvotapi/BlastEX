// Запрос «Коммутации»: контур уходит вместе со скважинами — по нему
// «Магистраль + цепочки» сверяет ряды с бровкой.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "./endpoints";
import type { BlockContour } from "../types/design";

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  fetchMock.mockImplementation(async () => new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } }));
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

function lastBody(): Record<string, unknown> {
  const [, init] = fetchMock.mock.calls.at(-1) as [string, RequestInit];
  return JSON.parse(String(init.body));
}

describe("api: построение коммутации", () => {
  it("контур передаётся; без него ключа нет", async () => {
    const contour = { vertices: [], free_faces: [[0, 1]] } as unknown as BlockContour;
    await api.design.tie([], "trunk_chains", { system: "nonel" } as never, contour);
    expect(lastBody().contour).toEqual(contour);
    await api.design.tie([], "row", { system: "nonel" } as never);
    expect(lastBody()).not.toHaveProperty("contour");
  });
});
