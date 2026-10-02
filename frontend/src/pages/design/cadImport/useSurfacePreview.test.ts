// @vitest-environment jsdom
// Предпросмотр кровли: запрос через 250 мс после правки, устаревший ответ не
// затирает свежий, без контура — нет кровли (TASK-013, PR 3).
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CadSurfaceRequest, CadSurfaceResult } from "../../../types/cad";
import { surfaceResult } from "./testing/fixtures";
import { useSurfacePreview } from "./useSurfacePreview";

function request(excluded: string[]): CadSurfaceRequest {
  return { top: [[0, 0], [1, 0], [1, 1]], bottom: null, roles: ["spot_heights"], excluded, floor_z_m: 410, crest_z_m: 420 };
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("useSurfacePreview", () => {
  it("быстрые правки — один запрос с последними данными", async () => {
    const fetcher = vi.fn(async (_id: string, _request: CadSurfaceRequest) => surfaceResult());
    const { rerender } = renderHook(({ value }) => useSurfacePreview("src", value, fetcher), {
      initialProps: { value: request([]) },
    });
    rerender({ value: request(["A"]) });
    rerender({ value: request(["A", "B"]) });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });

    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher.mock.calls[0][1]).toMatchObject({ excluded: ["A", "B"] });
  });

  it("ответ старого запроса, пришедший после нового, отбрасывается", async () => {
    const resolvers: Array<(value: CadSurfaceResult) => void> = [];
    const fetcher = vi.fn(() => new Promise<CadSurfaceResult>((resolve) => resolvers.push(resolve)));
    const { result: hook, rerender } = renderHook(({ value }) => useSurfacePreview("src", value, fetcher), {
      initialProps: { value: request([]) },
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });
    rerender({ value: request(["A"]) });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });

    await act(async () => {
      resolvers[1](surfaceResult({ builder: "свежий" }));
      resolvers[0](surfaceResult({ builder: "старый" }));
    });

    expect(hook.current.result?.builder).toBe("свежий");
    expect(hook.current.pending).toBe(false);
  });

  it("без запроса (контур не построен) кровли нет", () => {
    const fetcher = vi.fn(async () => surfaceResult());
    const { result: hook } = renderHook(() => useSurfacePreview("src", null, fetcher));

    expect(hook.current).toEqual({ result: null, pending: false, error: "" });
    expect(fetcher).not.toHaveBeenCalled();
  });
});
