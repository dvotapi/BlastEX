// @vitest-environment jsdom
// Ситуация объекта на странице «Проектирование» (TASK-013, PR 4): каталог по
// ссылке паспорта, геометрия показанных версий с кэшем по номеру правки,
// устаревшие ответы отбрасываются, удалённая версия не ломает остальные.
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CadSituationCatalogue, CadSituationGeometry } from "../../types/cad";
import { emptyDesign, type BlastDesign } from "../../types/design";
import { SITUATION_DELAY_MS, situationReferenceIds, useSituation, useSituationChoice, type SituationFetchers } from "./useSituation";

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

function version(source_id: string, survey_date: string, revision = 1) {
  return {
    source_id,
    title: "Положение горных работ",
    file_name: `${source_id}.dxf`,
    survey_date,
    uploaded_at: "2026-10-01T10:00:00+00:00",
    situation_count: 4,
    revision,
  };
}

function catalogue(extra: Partial<CadSituationCatalogue> = {}, revision = 1): CadSituationCatalogue {
  return {
    site_code: "SITE_ZK",
    crs: null,
    missing: [],
    truncated: false,
    series: [
      {
        key: "положение горных работ",
        title: "Положение горных работ",
        versions: [version("oct", "2026-10-01", revision), version("sep", "2026-09-01")],
        default_source_id: "oct",
      },
      {
        key: "блок 70",
        title: "блок 70",
        versions: [version("block", "2026-09-28")],
        default_source_id: "block",
      },
    ],
    ...extra,
  };
}

function geometry(source_id: string, revision = 1): CadSituationGeometry {
  return { source_id, revision, title: source_id, survey_date: null, layers: [], warnings: [] };
}

function fetchers(overrides: Partial<SituationFetchers> = {}): SituationFetchers {
  return {
    catalogue: vi.fn(async () => catalogue()),
    geometry: vi.fn(async (id: string) => geometry(id)),
    ...overrides,
  };
}

async function settle() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(SITUATION_DELAY_MS + 10);
  });
}

describe("situationReferenceIds", () => {
  const base = emptyDesign();
  const cad = { source_id: "block", file_name: "блок.dxf" } as NonNullable<BlastDesign["contour"]["cad"]>;

  it("ссылка на версии ситуации — главнее источника контура", () => {
    expect(
      situationReferenceIds({
        ...base,
        contour: { ...base.contour, cad: { ...cad, situation: [{ source_id: "sep", title: "", survey_date: null }] } },
      }),
    ).toEqual(["sep"]);
  });

  it("без ссылки — источник контура, без чертежа — ничего", () => {
    expect(situationReferenceIds({ ...base, contour: { ...base.contour, cad } })).toEqual(["block"]);
    expect(situationReferenceIds(base)).toEqual([]);
  });
});

describe("useSituation", () => {
  it("каталог по ссылке паспорта, затем геометрия версий по умолчанию", async () => {
    const api = fetchers();
    const { result } = renderHook(() => useSituation(["block"], {}, 0, api));

    expect(api.catalogue).not.toHaveBeenCalled();
    await settle();
    await settle();

    expect(api.catalogue).toHaveBeenCalledWith(["block"]);
    expect(api.geometry).toHaveBeenCalledWith("oct");
    expect(api.geometry).toHaveBeenCalledWith("block");
    expect(result.current.shown.map((item) => [item.seriesKey, item.geometry.source_id])).toEqual([
      ["положение горных работ", "oct"],
      ["блок 70", "block"],
    ]);
    expect(result.current.displayed).toEqual({ "положение горных работ": "oct", "блок 70": "block" });
  });

  it("версия, выбранная в «Виде», заменяет версию по умолчанию", async () => {
    const api = fetchers();
    const { result } = renderHook(() => useSituation([], { "положение горных работ": "sep" }, 0, api));
    await settle();
    await settle();

    expect(api.geometry).toHaveBeenCalledWith("sep");
    expect(api.geometry).not.toHaveBeenCalledWith("oct");
    expect(result.current.displayed["положение горных работ"]).toBe("sep");
  });

  it("версии из ссылки паспорта видны отдельно — для подписи «паспорт: дата»", async () => {
    const { result } = renderHook(() => useSituation(["sep", "block"], {}, 0, fetchers()));
    await settle();

    expect(result.current.passport).toEqual({ "положение горных работ": "sep", "блок 70": "block" });
  });

  it("устаревший ответ каталога не применяется", async () => {
    let releaseFirst: (value: CadSituationCatalogue) => void = () => undefined;
    const api = fetchers({
      catalogue: vi
        .fn()
        .mockImplementationOnce(() => new Promise<CadSituationCatalogue>((resolve) => (releaseFirst = resolve)))
        .mockImplementationOnce(async () => catalogue({ series: [] })),
    });
    const { result, rerender } = renderHook(({ ids }) => useSituation(ids, {}, 0, api), { initialProps: { ids: ["a"] } });
    await settle();
    rerender({ ids: ["b"] });
    await settle();
    await act(async () => releaseFirst(catalogue()));

    expect(result.current.catalogue?.series).toEqual([]);
  });

  it("геометрия кэшируется по номеру правки источника", async () => {
    const api = fetchers();
    const { rerender } = renderHook(({ reload }) => useSituation([], {}, reload, api), { initialProps: { reload: 0 } });
    await settle();
    await settle();
    expect(api.geometry).toHaveBeenCalledTimes(2);

    rerender({ reload: 1 });
    await settle();
    await settle();
    expect(api.geometry).toHaveBeenCalledTimes(2);

    (api.catalogue as ReturnType<typeof vi.fn>).mockImplementation(async () => catalogue({}, 2));
    rerender({ reload: 2 });
    await settle();
    await settle();
    expect(api.geometry).toHaveBeenCalledTimes(3);
    expect(api.geometry).toHaveBeenLastCalledWith("oct");
  });

  it("удалённая версия — в «missing», остальные показываются, повторов нет", async () => {
    const api = fetchers({
      catalogue: vi.fn(async () => catalogue({ missing: ["gone"] })),
      geometry: vi.fn(async (id: string) => {
        if (id === "oct") throw new Error("Импорт чертежа не найден.");
        return geometry(id);
      }),
    });
    const { result, rerender } = renderHook(({ reload }) => useSituation(["gone"], {}, reload, api), {
      initialProps: { reload: 0 },
    });
    await settle();
    await settle();

    expect(result.current.missing).toEqual(["gone", "oct"]);
    expect(result.current.shown.map((item) => item.geometry.source_id)).toEqual(["block"]);

    rerender({ reload: 0 });
    await settle();
    expect(api.geometry).toHaveBeenCalledTimes(2);
  });

  it("ошибка каталога видна, ситуации нет", async () => {
    const { result } = renderHook(() =>
      useSituation([], {}, 0, fetchers({ catalogue: vi.fn(async () => Promise.reject(new Error("сеть"))) })),
    );
    await settle();

    expect(result.current.error).toMatch(/ситуацию объекта/);
    expect(result.current.shown).toEqual([]);
  });
});

describe("useSituationChoice", () => {
  it("выбор даты — только у своего паспорта: другой паспорт открывается со своей ситуацией", () => {
    const { result, rerender } = renderHook(({ id }) => useSituationChoice(id), { initialProps: { id: "passport-a" } });

    act(() => result.current[1]("положение горных работ", "sep"));
    expect(result.current[0]).toEqual({ "положение горных работ": "sep" });

    rerender({ id: "passport-a" });
    expect(result.current[0]).toEqual({ "положение горных работ": "sep" });

    rerender({ id: "passport-b" });
    expect(result.current[0]).toEqual({});
  });
});
