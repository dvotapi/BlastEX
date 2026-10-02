// Состояние шагов «Поверхность» и «Итог» (TASK-013, PR 3): запрос
// предпросмотра кровли, исключение отметок, подошва, готовность к построению
// и кровля для паспорта.
import { describe, expect, it } from "vitest";
import { emptyDesign } from "../../../types/design";
import { cadSource, contourResult, surfaceResult } from "./testing/fixtures";
import {
  buildBlocker,
  buildConfirmText,
  excludePoint,
  initialSurface,
  percentDiff,
  restorePoint,
  roofSurface,
  surfaceFloor,
  surfaceRequest,
  SURFACE_ROLES,
  toggleSurfaceRole,
} from "./surfaceState";

describe("surfaceState", () => {
  it("все роли поверхности включены, подошва — из контура, пока поле пустое", () => {
    const state = initialSurface(cadSource());

    expect(state.roles).toEqual(SURFACE_ROLES.map((role) => role.code));
    expect(state.floor).toBe("");
    expect(surfaceFloor(state, contourResult())).toBe(410);
    expect(surfaceFloor({ ...state, floor: "409,5" }, contourResult())).toBe(409.5);
  });

  it("явная подошва разбора попадает в поле", () => {
    const source = cadSource({ params: { scale: 1, label_radius_m: 3, floor_z_m: 405, bench_height_m: 10 } });

    expect(initialSurface(source).floor).toBe("405");
  });

  it("запрос — только для построенного контура: оба контура, роли, исключения, подошва и бровка", () => {
    const state = excludePoint(initialSurface(cadSource()), "51C");

    expect(surfaceRequest(state, null)).toBeNull();
    expect(surfaceRequest(state, contourResult({ ok: false }))).toBeNull();
    expect(surfaceRequest(state, contourResult())).toEqual({
      top: [[90, 170], [140, 170], [140, 215]],
      bottom: [[90, 170], [145, 170], [145, 215]],
      roles: ["crest_top", "crest_bottom", "feature_line", "contour_line", "spot_heights"],
      excluded: ["51C"],
      floor_z_m: 410,
      crest_z_m: 420.3,
    });
  });

  it("исключение и возврат отметки, роль снимается и ставится", () => {
    const state = initialSurface(cadSource());
    const excluded = excludePoint(excludePoint(state, "51C"), "51C");

    expect(excluded.excluded).toEqual(["51C"]);
    expect(restorePoint(excluded, "51C").excluded).toEqual([]);
    expect(toggleSurfaceRole(state, "contour_line").roles).not.toContain("contour_line");
    expect(toggleSurfaceRole(toggleSurfaceRole(state, "contour_line"), "contour_line").roles).toContain("contour_line");
  });

  it("расхождение с картой в процентах", () => {
    expect(percentDiff(110, 100)).toBeCloseTo(10);
    expect(percentDiff(110, null)).toBeNull();
    expect(percentDiff(null, 100)).toBeNull();
    expect(percentDiff(10, 0)).toBeNull();
  });

  it("блок не строится без кровли и без подтверждения высоты вне 2–25 м", () => {
    const state = initialSurface(cadSource());
    const unsure = surfaceResult({ bench: { floor_z_m: 410, mean_height_m: 0.6, needs_confirmation: true } });

    expect(buildBlocker(state, contourResult(), surfaceResult(), false)).toBeNull();
    expect(buildBlocker(state, contourResult(), null, false)).toMatch(/Кровля/);
    expect(buildBlocker(state, contourResult(), surfaceResult(), true)).toMatch(/Считаю/);
    expect(buildBlocker(state, contourResult(), surfaceResult({ ok: false }), false)).toMatch(/Кровля/);
    expect(buildBlocker(state, contourResult(), unsure, false)).toMatch(/Подтвердите высоту/);
    expect(buildBlocker({ ...state, confirmHeight: true }, contourResult(), unsure, false)).toBeNull();
  });

  it("кровля для паспорта: TIN в точках, определение из чертежа", () => {
    const state = excludePoint(initialSurface(cadSource()), "51C");

    const surface = roofSurface(surfaceResult(), cadSource(), state, "2026-10-02T10:00:00.000Z");

    expect(surface.kind).toBe("top");
    expect(surface.source_format).toBe("cad");
    expect(surface.source_name).toBe("блок 66.dwg");
    expect(surface.points).toEqual([]);
    expect(surface.tin.vertices[1]).toEqual({ x: 145, y: 170, z: 410 });
    expect(surface.tin.triangles).toEqual([
      [0, 1, 2],
      [0, 2, 3],
    ]);
    expect(surface.cad).toEqual({
      source_id: "src-1",
      file_name: "блок 66.dwg",
      roles: state.roles,
      excluded: ["51C"],
      builder: "cdt",
      floor_z_m: 410,
      quality: {
        spot_count: 206,
        coverage_pct: 99.93,
        max_gap_m: 10.91,
        outlier_count: 1,
        conflict_count: 1,
      },
      built_at: "2026-10-02T10:00:00.000Z",
    });
  });
});

describe("buildConfirmText", () => {
  const base = emptyDesign();
  const vertices = [
    { x: 0, y: 0, z: 420 },
    { x: 40, y: 0, z: 420 },
    { x: 40, y: 20, z: 420 },
  ];
  const model = (kind: "top" | "floor", name: string) => ({ ...roofSurface(surfaceResult(), cadSource(), initialSurface(cadSource()), "t"), kind, name });

  it("пустой паспорт — подтверждать нечего", () => {
    expect(buildConfirmText(base, 410)).toBeNull();
  });

  it("перечисляет, что сменится: контур, кровля, подошва, скважины", () => {
    const text = buildConfirmText(
      {
        ...base,
        contour: { ...base.contour, vertices },
        surfaces: { ...base.surfaces, top: model("top", "Съёмка 01.09"), floor: model("floor", "Подошва DXF") },
        holes: [{ id: "1" }, { id: "2" }] as unknown as typeof base.holes,
      },
      410,
    );

    expect(text).toContain("контур блока");
    expect(text).toContain("кровля «Съёмка 01.09» заменится кровлей из чертежа");
    expect(text).toContain("поверхность подошвы «Подошва DXF» снимется: подошва — отметка 410,0 м");
    expect(text).toContain("2 скважины, заряды и сеть очистятся");
  });
});
