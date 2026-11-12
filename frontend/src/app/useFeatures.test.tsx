// @vitest-environment jsdom
import { cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../api/endpoints", () => ({ api: { features: vi.fn() } }));

import { api } from "../api/endpoints";
import { useFeatures } from "./useFeatures";

afterEach(cleanup);

describe("useFeatures", () => {
  it("читает флаг паспорта на бурение", async () => {
    vi.mocked(api.features).mockResolvedValue({ intelligence: false, drill_passport: true });
    const { result } = renderHook(() => useFeatures());
    expect(result.current.drill_passport).toBe(false);
    await waitFor(() => expect(result.current.drill_passport).toBe(true));
  });

  it("читает флаг проекта МВ по форме ВМ.09.03", async () => {
    vi.mocked(api.features).mockResolvedValue({ intelligence: false, drill_passport: true, mass_blast_v2: true });
    const { result } = renderHook(() => useFeatures());
    await waitFor(() => expect(result.current.mass_blast_v2).toBe(true));
  });

  it("без ответа сервера разделы выключены", async () => {
    vi.mocked(api.features).mockRejectedValue(new Error("сеть"));
    const { result } = renderHook(() => useFeatures());
    await waitFor(() => expect(api.features).toHaveBeenCalled());
    expect(result.current).toEqual({ intelligence: false, drill_passport: false, mass_blast_v2: false });
  });
});
