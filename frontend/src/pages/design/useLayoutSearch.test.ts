// @vitest-environment jsdom
// Подбор раскладки: опрос статуса, остановка, возврат на страницу, смена
// паспорта, устаревший результат, отпечаток входов и ошибка 409.
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/endpoints";
import { HttpError } from "../../api/client";
import { emptyDesign, type LayoutSearchStatus } from "../../types/design";
import { LAYOUT_SEARCH_POLL_MS, layoutFingerprint, useLayoutSearch } from "./useLayoutSearch";

beforeEach(() => {
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

function status(over: Partial<LayoutSearchStatus> = {}): LayoutSearchStatus {
  return {
    state: "idle",
    stage: null,
    done: 0,
    total: 0,
    elapsed_s: null,
    fingerprint: null,
    result: null,
    error: null,
    ...over,
  };
}

const RESULT = { best: [], evaluated: 5, rejected: 1, stopped_early: false, elapsed_s: 3, all_rejected: false, warnings: [] };

const flush = () => act(async () => {});
const tick = (ms: number) => act(async () => { await vi.advanceTimersByTimeAsync(ms); });

describe("useLayoutSearch", () => {
  it("старт → опрос раз в секунду до done", async () => {
    vi.spyOn(api.design, "layoutSearchStatus")
      .mockResolvedValueOnce(status())
      .mockResolvedValueOnce(status({ state: "running", done: 1, total: 4 }))
      .mockResolvedValue(status({ state: "done", fingerprint: "fp", result: RESULT }));
    const startSpy = vi.spyOn(api.design, "layoutSearchStart").mockResolvedValue(status({ state: "running", total: 4 }));
    const { result } = renderHook(() => useLayoutSearch("d1", "fp"));
    await flush();
    expect(result.current.status?.state).toBe("idle");

    await act(async () => { await result.current.start(emptyDesign()); });
    expect(startSpy).toHaveBeenCalledWith("d1", expect.anything(), "fp");
    expect(result.current.status?.state).toBe("running");

    await tick(LAYOUT_SEARCH_POLL_MS);
    expect(result.current.status?.done).toBe(1);
    await tick(LAYOUT_SEARCH_POLL_MS);
    expect(result.current.status?.state).toBe("done");

    const calls = vi.mocked(api.design.layoutSearchStatus).mock.calls.length;
    await tick(LAYOUT_SEARCH_POLL_MS * 3);
    expect(vi.mocked(api.design.layoutSearchStatus).mock.calls.length).toBe(calls);
  });

  it("остановка кладёт ответ сервера в статус", async () => {
    vi.spyOn(api.design, "layoutSearchStatus").mockResolvedValue(status({ state: "running" }));
    const stopSpy = vi.spyOn(api.design, "layoutSearchStop").mockResolvedValue(status({ state: "stopped", result: RESULT }));
    const { result } = renderHook(() => useLayoutSearch("d1", "fp"));
    await flush();
    await act(async () => { await result.current.stop(); });
    expect(stopSpy).toHaveBeenCalledWith("d1");
    expect(result.current.status?.state).toBe("stopped");
    const calls = vi.mocked(api.design.layoutSearchStatus).mock.calls.length;
    await tick(LAYOUT_SEARCH_POLL_MS * 3);
    expect(vi.mocked(api.design.layoutSearchStatus).mock.calls.length).toBe(calls);
  });

  it("возврат на страницу при идущем подборе продолжает опрос", async () => {
    const spy = vi.spyOn(api.design, "layoutSearchStatus")
      .mockResolvedValueOnce(status({ state: "running", done: 2, total: 9 }))
      .mockResolvedValue(status({ state: "running", done: 3, total: 9 }));
    const first = renderHook(() => useLayoutSearch("d1", "fp"));
    await flush();
    first.unmount();
    const second = renderHook(() => useLayoutSearch("d1", "fp"));
    await flush();
    expect(second.result.current.status?.state).toBe("running");
    await tick(LAYOUT_SEARCH_POLL_MS);
    expect(second.result.current.status?.done).toBe(3);
    expect(spy.mock.calls.length).toBeGreaterThanOrEqual(3);
  });

  it("смена designId отбрасывает запоздалый ответ старого", async () => {
    let resolveOld: (s: LayoutSearchStatus) => void = () => {};
    vi.spyOn(api.design, "layoutSearchStatus").mockImplementation((id: string) =>
      id === "old"
        ? new Promise<LayoutSearchStatus>((resolve) => { resolveOld = resolve; })
        : Promise.resolve(status({ state: "done", fingerprint: "x", result: RESULT })),
    );
    const { result, rerender } = renderHook(({ id }) => useLayoutSearch(id, "x"), { initialProps: { id: "old" } });
    rerender({ id: "new" });
    await flush();
    expect(result.current.status?.state).toBe("done");
    await act(async () => { resolveOld(status({ state: "running" })); });
    expect(result.current.status?.state).toBe("done");
  });

  it("stale: результат есть, а отпечаток другой", async () => {
    vi.spyOn(api.design, "layoutSearchStatus").mockResolvedValue(status({ state: "done", fingerprint: "a", result: RESULT }));
    const { result, rerender } = renderHook(({ fp }) => useLayoutSearch("d1", fp), { initialProps: { fp: "a" } });
    await flush();
    expect(result.current.stale).toBe(false);
    rerender({ fp: "b" });
    expect(result.current.stale).toBe(true);
  });

  it("409 попадает в error с текстом сервера", async () => {
    vi.spyOn(api.design, "layoutSearchStatus").mockResolvedValue(status());
    vi.spyOn(api.design, "layoutSearchStart").mockRejectedValue(
      new HttpError("Подбор раскладки уже идёт: блок «Б-7». Дождитесь окончания или остановите его.", 409),
    );
    const { result } = renderHook(() => useLayoutSearch("d1", "fp"));
    await flush();
    await act(async () => { await result.current.start(emptyDesign()); });
    expect(result.current.error).toContain("Подбор раскладки уже идёт");
  });
});

describe("useLayoutSearch: сбои и гонки", () => {
  it("сбой запроса статуса при running: ошибка видна, опрос продолжается, успех её снимает", async () => {
    vi.spyOn(api.design, "layoutSearchStatus")
      .mockResolvedValueOnce(status({ state: "running", done: 1, total: 4 }))
      .mockRejectedValueOnce(new Error("Сеть недоступна"))
      .mockResolvedValue(status({ state: "running", done: 2, total: 4 }));
    const { result } = renderHook(() => useLayoutSearch("d1", "fp"));
    await flush();
    await tick(LAYOUT_SEARCH_POLL_MS);
    expect(result.current.error).toBe("Сеть недоступна");
    expect(result.current.status?.state).toBe("running");
    await tick(LAYOUT_SEARCH_POLL_MS);
    expect(result.current.status?.done).toBe(2);
    expect(result.current.error).toBeNull();
  });

  it.each([401, 403, 404])("постоянная ошибка %i при running — опрос прекращается", async (code) => {
    const poll = vi.spyOn(api.design, "layoutSearchStatus")
      .mockResolvedValueOnce(status({ state: "running", done: 1, total: 4 }))
      .mockRejectedValue(new HttpError("Сессия истекла", code));
    const { result } = renderHook(() => useLayoutSearch("d1", "fp"));
    await flush();
    await tick(LAYOUT_SEARCH_POLL_MS);
    expect(result.current.error).toBe("Сессия истекла");
    expect(poll).toHaveBeenCalledTimes(2);
    await tick(LAYOUT_SEARCH_POLL_MS * 5);
    expect(poll).toHaveBeenCalledTimes(2);
  });

  it("сбой сервера 5xx при running — опрос продолжается", async () => {
    const poll = vi.spyOn(api.design, "layoutSearchStatus")
      .mockResolvedValueOnce(status({ state: "running", done: 1, total: 4 }))
      .mockRejectedValue(new HttpError("Сервер недоступен", 502));
    renderHook(() => useLayoutSearch("d1", "fp"));
    await flush();
    await tick(LAYOUT_SEARCH_POLL_MS * 3);
    expect(poll).toHaveBeenCalledTimes(4);
  });

  it("поздний ответ опроса до старта не перетирает running от старта", async () => {
    let resolvePoll: (s: LayoutSearchStatus) => void = () => {};
    vi.spyOn(api.design, "layoutSearchStatus")
      .mockImplementationOnce(() => new Promise<LayoutSearchStatus>((r) => { resolvePoll = r; }))
      .mockResolvedValue(status({ state: "running", done: 1, total: 4 }));
    vi.spyOn(api.design, "layoutSearchStart").mockResolvedValue(status({ state: "running", total: 4 }));
    const { result } = renderHook(() => useLayoutSearch("d1", "fp"));
    await act(async () => { await result.current.start(emptyDesign()); });
    await act(async () => { resolvePoll(status()); });
    expect(result.current.status?.state).toBe("running");
    await tick(LAYOUT_SEARCH_POLL_MS);
    expect(result.current.status?.done).toBe(1);
  });

  it("старт без отпечатка не шлёт запрос и даёт ошибку", async () => {
    vi.spyOn(api.design, "layoutSearchStatus").mockResolvedValue(status());
    const startSpy = vi.spyOn(api.design, "layoutSearchStart");
    const { result } = renderHook(() => useLayoutSearch("d1", null));
    await flush();
    await act(async () => { await result.current.start(emptyDesign()); });
    expect(startSpy).not.toHaveBeenCalled();
    expect(result.current.error).toBe("Подождите, данные блока ещё готовятся.");
  });

  it("при размонтировании таймеров не остаётся", async () => {
    vi.spyOn(api.design, "layoutSearchStatus").mockResolvedValue(status({ state: "running" }));
    const { unmount } = renderHook(() => useLayoutSearch("d1", "fp"));
    await flush();
    expect(vi.getTimerCount()).toBe(1);
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});

describe("layoutFingerprint", () => {
  it("ключ undefined равен отсутствующему, 1 равно 1.0", async () => {
    const a = { contour: { a: 1, b: undefined }, surfaces: {}, domains: [], pattern_params: {}, rock_name: "r" };
    const b = { contour: { a: 1.0 }, surfaces: {}, domains: [], pattern_params: {}, rock_name: "r" };
    expect(await layoutFingerprint(a)).toBe(await layoutFingerprint(b));
  });

  it("без crypto.subtle работает запасной хеш, различающий входы", async () => {
    vi.stubGlobal("crypto", { subtle: undefined });
    try {
      const base = { contour: { a: 1 }, surfaces: {}, domains: [], pattern_params: {}, rock_name: "r" };
      const fp = await layoutFingerprint(base);
      expect(fp).toMatch(/^[0-9a-f]+$/);
      expect(await layoutFingerprint({ ...base })).toBe(fp);
      expect(await layoutFingerprint({ ...base, contour: { a: 2 } })).not.toBe(fp);
    } finally {
      vi.unstubAllGlobals();
    }
  });
});

describe("layoutFingerprint: основной путь", () => {
  const base = { contour: { a: 1, b: [1, 2] }, surfaces: {}, domains: [], pattern_params: { x: 1, y: 2 }, rock_name: "Гранит" };

  it("не зависит от порядка ключей", async () => {
    const reordered = { rock_name: "Гранит", pattern_params: { y: 2, x: 1 }, domains: [], surfaces: {}, contour: { b: [1, 2], a: 1 } };
    expect(await layoutFingerprint(reordered)).toBe(await layoutFingerprint(base));
  });

  it("меняется при правке контура", async () => {
    const edited = { ...base, contour: { a: 2, b: [1, 2] } };
    expect(await layoutFingerprint(edited)).not.toBe(await layoutFingerprint(base));
    expect(await layoutFingerprint(base)).toMatch(/^[0-9a-f]{64}$/);
  });
});
