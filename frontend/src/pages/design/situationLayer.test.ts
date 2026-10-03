import { describe, expect, it } from "vitest";
import type { CadSituationGeometry, CadSituationLayer } from "../../types/cad";
import { situation3dLines, situationColor, situationLayerKey, situationPanelSeries, situationSegments, situationStrokes } from "./situationLayer";

function layer(name: string, extra: Partial<CadSituationLayer> = {}): CadSituationLayer {
  return {
    name,
    kind: "road",
    kind_label: "Дорога",
    color: "#ff0000",
    lines: [
      {
        points: [
          [100, 200, 0],
          [110, 200, 0],
          [110, 210, 0],
        ],
        closed: false,
      },
    ],
    points: [],
    vertex_count: 3,
    omitted: false,
    ...extra,
  };
}

function geometry(layers: CadSituationLayer[], source_id = "src-9"): CadSituationGeometry {
  return { source_id, revision: 1, title: "Положение горных работ", survey_date: "2026-09-01", layers, warnings: [] };
}

const CAMERA = { x: 100, y: 200, scale: 2 };
const VIEWPORT = { width: 400, height: 300 };

describe("situationColor", () => {
  it("белый и почти белый на светлом плане — тёмно-серый", () => {
    expect(situationColor("#ffffff")).toBe("#3a4540");
    expect(situationColor("#f0f0ee")).toBe("#3a4540");
  });

  it("обычный цвет DXF — как есть, без цвета — серый", () => {
    expect(situationColor("#ff0000")).toBe("#ff0000");
    expect(situationColor("#00ffff")).toBe("#00ffff");
    expect(situationColor(null)).toBe("#6e7c75");
  });
});

describe("situationStrokes", () => {
  it("видимые слои — в экранных координатах плана, по штриху на слой", () => {
    const strokes = situationStrokes(
      [{ seriesKey: "положение", geometry: geometry([layer("Дорога"), layer("ЛЭП", { color: "#ffffff" })]) }],
      new Set(),
      CAMERA,
      VIEWPORT,
    );

    expect(strokes.map((item) => item.key)).toEqual([
      situationLayerKey("положение", "Дорога"),
      situationLayerKey("положение", "ЛЭП"),
    ]);
    expect(strokes[0].color).toBe("#ff0000");
    expect(strokes[1].color).toBe("#3a4540");
    // Центр камеры — центр экрана; ось Y вниз.
    expect(strokes[0].polylines[0]).toEqual([200, 150, 220, 150, 220, 130]);
  });

  it("скрытые и не вошедшие в ответ слои не рисуются", () => {
    const strokes = situationStrokes(
      [
        {
          seriesKey: "положение",
          geometry: geometry([layer("Дорога"), layer("Склад"), layer("Здания", { omitted: true, lines: [] })]),
        },
      ],
      new Set([situationLayerKey("положение", "Склад")]),
      CAMERA,
      VIEWPORT,
    );

    expect(strokes.map((item) => item.key)).toEqual([situationLayerKey("положение", "Дорога")]);
  });

  it("замкнутая линия возвращается в начало, точки — отдельно", () => {
    const strokes = situationStrokes(
      [
        {
          seriesKey: "блок",
          geometry: geometry([
            layer("Склад", {
              lines: [
                {
                  points: [
                    [100, 200, 0],
                    [110, 200, 0],
                    [110, 210, 0],
                  ],
                  closed: true,
                },
              ],
              points: [[105, 205, 420]],
            }),
          ]),
        },
      ],
      new Set(),
      CAMERA,
      VIEWPORT,
    );

    expect(strokes[0].polylines[0]).toEqual([200, 150, 220, 150, 220, 130, 200, 150]);
    expect(strokes[0].points).toEqual([210, 140]);
  });
});

describe("situation3dLines", () => {
  it("линии без отметки ложатся на отметку бровки, с отметкой — на свою", () => {
    const lines = situation3dLines(
      [
        {
          seriesKey: "положение",
          geometry: geometry([
            layer("Дорога"),
            layer("Отвал", {
              lines: [
                {
                  points: [
                    [0, 0, 421.5],
                    [5, 0, 421.8],
                  ],
                  closed: false,
                },
              ],
            }),
          ]),
        },
      ],
      new Set(),
      420,
    );

    expect(lines[0].points.map((point) => point.z)).toEqual([420, 420, 420]);
    expect(lines[1].points.map((point) => point.z)).toEqual([421.5, 421.8]);
    expect(lines[0].color).toBe("#ff0000");
  });
});

describe("situationPanelSeries", () => {
  it("серии каталога: даты версий, версия паспорта, слои показанной версии", () => {
    const catalogue = {
      site_code: "SITE_ZK",
      crs: null,
      missing: [],
      truncated: false,
      series: [
        {
          key: "положение",
          title: "Положение горных работ",
          versions: [
            { source_id: "src-9", title: "Положение горных работ", file_name: "a.dxf", survey_date: "2026-09-01", uploaded_at: "", situation_count: 1, revision: 1 },
            { source_id: "src-0", title: "Положение горных работ", file_name: "без даты.dxf", survey_date: null, uploaded_at: "", situation_count: 1, revision: 1 },
          ],
          default_source_id: "src-9",
        },
      ],
    };
    const series = situationPanelSeries(
      catalogue,
      [{ seriesKey: "положение", geometry: geometry([layer("Дорога", { color: "#ffffff" })]) }],
      { положение: "src-9" },
      { положение: "src-0" },
    );

    expect(series).toEqual([
      {
        key: "положение",
        title: "Положение горных работ",
        versions: [
          { sourceId: "src-9", label: "01.09.2026" },
          { sourceId: "src-0", label: "без даты.dxf" },
        ],
        displayedId: "src-9",
        passportId: "src-0",
        layers: [{ key: situationLayerKey("положение", "Дорога"), name: "Дорога", color: "#3a4540", kindLabel: "Дорога", omitted: false }],
      },
    ]);
    expect(situationPanelSeries(catalogue, [], { положение: "src-9" }, {})[0].layers).toBeNull();
  });
});

describe("situationPanelSeries: версии одной даты", () => {
  it("одинаковые даты съёмки различаются временем загрузки", () => {
    const version = (source_id: string, uploaded_at: string) => ({
      source_id,
      title: "Положение горных работ",
      file_name: "п.dxf",
      survey_date: "2026-09-01",
      uploaded_at,
      situation_count: 1,
      revision: 1,
    });
    const catalogue = {
      site_code: "SITE_ZK",
      crs: null,
      missing: [],
      truncated: false,
      series: [
        {
          key: "положение",
          title: "Положение горных работ",
          versions: [
            version("b", "2026-10-03T03:31:14.5+00:00"),
            version("a", "2026-10-02T18:05:00+00:00"),
            { ...version("c", "2026-09-02T10:00:00+00:00"), survey_date: "2026-08-01" },
          ],
          default_source_id: "b",
        },
      ],
    };

    expect(situationPanelSeries(catalogue, [], {}, {})[0].versions.map((item) => item.label)).toEqual([
      "01.09.2026 · загружен 03.10.2026 03:31",
      "01.09.2026 · загружен 02.10.2026 18:05",
      "01.08.2026",
    ]);
  });
});

describe("situationSegments (3D)", () => {
  it("линии одного цвета — одна пачка отрезков от общей точки отсчёта", () => {
    const { origin, batches } = situationSegments([
      { color: "#ff0000", points: [{ x: 100, y: 200, z: 420 }, { x: 110, y: 200, z: 420 }, { x: 110, y: 210, z: 421 }] },
      { color: "#ff0000", points: [{ x: 100, y: 205, z: 420 }, { x: 105, y: 205, z: 420 }] },
      { color: "#3a4540", points: [{ x: 90, y: 190, z: 410 }, { x: 95, y: 190, z: 410 }] },
    ]);

    expect(origin).toEqual({ x: 100, y: 200, z: 420 });
    expect(batches.map((item) => item.color)).toEqual(["#ff0000", "#3a4540"]);
    // Три отрезка красных линий — по две вершины (x, высота, −y) на отрезок.
    expect(Array.from(batches[0].positions)).toEqual([
      0, 0, -0, 10, 0, -0,
      10, 0, -0, 10, 1, -10,
      0, 0, -5, 5, 0, -5,
    ]);
    expect(batches[1].positions).toHaveLength(6);
  });

  it("пусто — без пачек", () => {
    expect(situationSegments([])).toEqual({ origin: null, batches: [] });
  });
});
