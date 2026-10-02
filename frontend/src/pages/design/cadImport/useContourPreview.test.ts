// @vitest-environment jsdom
// Предпросмотр контура: запрос после паузы в правках, устаревший ответ не
// затирает свежий (TASK-013, PR 2).
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CadContourRequest, CadContourResult } from "../../../types/cad";
import { useContourPreview } from "./useContourPreview";

function result(method: string): CadContourResult {
  return {
    ok: true,
    method: method as CadContourResult["method"],
    issues: [],
    warnings: [],
    top: null,
    bottom: null,
    mean_area_m2: null,
    free_faces: [],
    flanks: [],
    closings: [],
    items: [],
    item_info: [],
    bench: { crest_z_m: null, toe_z_m: null, height_m: null, crest_source: "", toe_source: "" },
    crest_line: null,
  };
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("useContourPreview", () => {
  it("три быстрые правки — один запрос", async () => {
    const fetcher = vi.fn(async (_id: string, request: CadContourRequest) => result(request.method));
    const { rerender } = renderHook(({ request }) => useContourPreview("src", request, fetcher), {
      initialProps: { request: { method: "ready", handle: "1" } as CadContourRequest },
    });
    rerender({ request: { method: "ready", handle: "2" } });
    rerender({ request: { method: "ready", handle: "3" } });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });

    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher.mock.calls[0][1]).toMatchObject({ handle: "3" });
  });

  it("ответ старого запроса, пришедший после нового, игнорируется", async () => {
    const resolvers: Array<(value: CadContourResult) => void> = [];
    const fetcher = vi.fn(
      (_id: string, _request: CadContourRequest) => new Promise<CadContourResult>((resolve) => resolvers.push(resolve)),
    );
    const { result: hook, rerender } = renderHook(({ request }) => useContourPreview("src", request, fetcher), {
      initialProps: { request: { method: "ready", handle: "old" } as CadContourRequest },
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });
    rerender({ request: { method: "click", point: [1, 2] } });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });

    await act(async () => {
      resolvers[1](result("click"));
      resolvers[0](result("ready"));
    });

    expect(hook.current.result?.method).toBe("click");
    expect(hook.current.pending).toBe(false);
  });

  it("без запроса — нет результата", () => {
    const fetcher = vi.fn();
    const { result: hook } = renderHook(() => useContourPreview("src", null, fetcher));
    expect(hook.current.result).toBeNull();
    expect(fetcher).not.toHaveBeenCalled();
  });
});
