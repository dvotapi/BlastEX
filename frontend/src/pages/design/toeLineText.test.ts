import { describe, expect, it } from "vitest";
import type { BlockContour } from "../../types/design";
import { hasSurveyToe, lspToeTitle, SURVEY_TOE_TITLE, toeLineWarning } from "./toeLineText";

const BENCH = { crest_z_m: 0, toe_z_m: -10, face_angle_deg: 75 };

function contour(cad: { bottom?: [number, number][]; edited?: boolean } | null): BlockContour {
  // Для проверки нужны только нижний контур и отметка правки.
  return { vertices: [], free_faces: [], bench: BENCH, name: "Блок", cad: cad as unknown as BlockContour["cad"] };
}

describe("линия подошвы: подписи (решение 07.11.2026)", () => {
  it("по умолчанию — по углу, без «причины»", () => {
    expect(lspToeTitle({ source: "angle", polylines: [], reason: "default" }, 75)).toBe(
      "Подошва для ЛСП — по углу откоса 15° от вертикали",
    );
  });

  it("угол 90° — не задан: 15° по умолчанию, а не «совпадает с бровкой»", () => {
    expect(lspToeTitle({ source: "angle", polylines: [], reason: "default" }, 90)).toBe(
      "Подошва для ЛСП — по углу откоса 15° от вертикали (угол не задан)",
    );
  });

  it("выбрана съёмка, но её нет — причина видна", () => {
    expect(lspToeTitle({ source: "angle", polylines: [], reason: "no_survey" }, 70)).toBe(
      "Подошва для ЛСП — по углу откоса 20° от вертикали: нижней бровки в паспорте нет",
    );
  });

  it("съёмка для сравнения подписана", () => {
    expect(SURVEY_TOE_TITLE).toBe("Нижняя бровка по съёмке — для сравнения, ЛСП считается по углу");
  });

  it("предупреждение сводки — только про выбранную съёмку", () => {
    expect(toeLineWarning({ source: "angle", polylines: [], reason: "default" })).toBe("");
    expect(toeLineWarning({ source: "angle", polylines: [], reason: "survey_unmatched" })).not.toBe("");
  });

  it("съёмка годится, если нижний контур есть и контур не правили", () => {
    const ring: [number, number][] = [[0, 0], [1, 0], [1, 1]];
    expect(hasSurveyToe(contour(null))).toBe(false);
    expect(hasSurveyToe(contour({ bottom: ring }))).toBe(true);
    expect(hasSurveyToe(contour({ bottom: ring, edited: true }))).toBe(false);
    expect(hasSurveyToe(contour({ bottom: ring.slice(0, 2) }))).toBe(false);
  });
});
