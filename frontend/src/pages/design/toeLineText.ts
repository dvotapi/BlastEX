// Подписи линии подошвы, от которой считается ЛСП (`toe_line` пересчёта скважин).
import { ruNumber } from "../../lib/format";
import { DEFAULT_FACE_ANGLE_FROM_VERTICAL_DEG } from "../../lib/faceAngle";
import type { BlockContour, ToeLine } from "../../types/design";

// Причины, по которым выбранная на блоке съёмка не годится и подошва — по углу.
const ANGLE_TOE_REASON: Record<string, string> = {
  no_survey: "нижней бровки в паспорте нет",
  edited: "контур правили после построения — нижняя бровка из чертежа не используется",
  survey_unmatched: "откос при импорте не найден (нижний контур совпал с верхним) — постройте контур заново",
};

/** Подсказка к снятой нижней бровке, когда ЛСП — по углу (пунктир для сравнения). */
export const SURVEY_TOE_TITLE = "Нижняя бровка по съёмке — для сравнения, ЛСП считается по углу";

/**
 * Подсказка к линии подошвы для ЛСП: откуда она взята и почему по углу.
 * Угол 90° — «не задан»: сервер строит подошву с 15° от вертикали
 * (`toe_line.effective_face_angle_deg`).
 */
export function lspToeTitle(line: ToeLine, faceAngleDeg: number): string {
  if (line.source === "survey") return "Подошва для ЛСП — нижняя бровка из чертежа";
  const reason = ANGLE_TOE_REASON[line.reason ?? ""];
  const tail = reason ? `: ${reason}` : "";
  const unset = !(faceAngleDeg < 90);
  const fromVertical = unset ? DEFAULT_FACE_ANGLE_FROM_VERTICAL_DEG : 90 - faceAngleDeg;
  return `Подошва для ЛСП — по углу откоса ${ruNumber(fromVertical, 0)}° от вертикали${unset ? " (угол не задан)" : ""}${tail}`;
}

/** Предупреждение для сводки: выбранный откос из чертежа не учтён, ЛСП — по углу. */
export function toeLineWarning(line: ToeLine | null): string {
  if (line?.source !== "angle" || line.reason !== "survey_unmatched") return "";
  return "Откос из чертежа не учтён: нижний контур совпал с верхним, ЛСП считается по углу откоса — постройте контур заново.";
}

/** Есть ли снятая нижняя бровка для выбора «по съёмке» (как `geometry.drawing_bottom`). */
export function hasSurveyToe(contour: BlockContour): boolean {
  const cad = contour.cad;
  return Boolean(cad && !cad.edited && (cad.bottom?.length ?? 0) >= 3);
}
