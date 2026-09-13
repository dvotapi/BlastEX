// @vitest-environment jsdom
import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { GeometryRequest } from "../../api/endpoints";
import { useHoleGeometry } from "./useHoleGeometry";

const api = vi.hoisted(() => ({ geometry: vi.fn() }));
vi.mock("../../api/endpoints", () => ({ api }));

const payload = (undercharge_m: number) => ({ undercharge_m, view: "charge" }) as unknown as GeometryRequest;
const response = (label: string) => ({ label, hole_rows: [], block_rows: [] });

beforeEach(() => vi.clearAllMocks());

describe("useHoleGeometry", () => {
  it("запрашивает схему и повторяет запрос только при изменении содержимого", async () => {
    api.geometry.mockResolvedValue(response("A"));
    const { result, rerender } = renderHook(({ p }) => useHoleGeometry(p), { initialProps: { p: payload(2.7) } });
    await waitFor(() => expect(result.current.geometry?.label).toBe("A"));
    rerender({ p: payload(2.7) });
    expect(api.geometry).toHaveBeenCalledTimes(1);
    api.geometry.mockResolvedValue(response("B"));
    rerender({ p: payload(3.1) });
    await waitFor(() => expect(result.current.geometry?.label).toBe("B"));
    expect(api.geometry).toHaveBeenCalledTimes(2);
  });

  it("ответ на устаревший запрос отбрасывается", async () => {
    let resolveOld: (value: unknown) => void = () => {};
    api.geometry
      .mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve; }))
      .mockResolvedValueOnce(response("новый"));
    const { result, rerender } = renderHook(({ p }) => useHoleGeometry(p), { initialProps: { p: payload(1) } });
    await waitFor(() => expect(api.geometry).toHaveBeenCalledTimes(1));
    rerender({ p: payload(2) });
    await waitFor(() => expect(result.current.geometry?.label).toBe("новый"));
    resolveOld(response("старый"));
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(result.current.geometry?.label).toBe("новый");
  });

  it("серия быстрых правок уходит одним запросом, а пересчёт виден сразу", async () => {
    api.geometry.mockResolvedValue(response("итог"));
    const { result, rerender } = renderHook(({ p }) => useHoleGeometry(p), { initialProps: { p: payload(1) } });
    expect(result.current.loading).toBe(true);
    rerender({ p: payload(1.1) });
    rerender({ p: payload(1.2) });
    rerender({ p: payload(1.3) });
    await waitFor(() => expect(result.current.geometry?.label).toBe("итог"));
    expect(api.geometry).toHaveBeenCalledTimes(1);
    expect(api.geometry).toHaveBeenCalledWith(payload(1.3));
    expect(result.current.loading).toBe(false);
  });

  it("без запроса схемы нет", async () => {
    api.geometry.mockResolvedValue(response("A"));
    const { result, rerender } = renderHook(({ p }) => useHoleGeometry(p), {
      initialProps: { p: payload(1) as GeometryRequest | null },
    });
    await waitFor(() => expect(result.current.geometry).not.toBeNull());
    rerender({ p: null });
    await waitFor(() => expect(result.current.geometry).toBeNull());
  });

  it("ошибку показывает, прошлую схему не стирает", async () => {
    api.geometry.mockResolvedValueOnce(response("A")).mockRejectedValueOnce(new Error("Сбой"));
    const { result, rerender } = renderHook(({ p }) => useHoleGeometry(p), { initialProps: { p: payload(1) } });
    await waitFor(() => expect(result.current.geometry?.label).toBe("A"));
    rerender({ p: payload(2) });
    await waitFor(() => expect(result.current.error).toBe("Сбой"));
    expect(result.current.geometry?.label).toBe("A");
  });
});
