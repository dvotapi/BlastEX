// Подписи линии подошвы, от которой считается ЛСП (`toe_line` пересчёта скважин).
import { ruNumber } from "../../lib/format";
import type { ToeLine } from "../../types/design";

const ANGLE_TOE_REASON: Record<string, string> = {
  no_survey: "нижней бровки в паспорте нет",
  edited: "контур правили после построения — нижняя бровка из чертежа не используется",
  survey_unmatched: "откос при импорте не найден (нижний контур совпал с верхним) — постройте контур заново",
};

/** Подсказка к линии подошвы для ЛСП: откуда она взята и почему по углу. */
export function lspToeTitle(line: ToeLine, faceAngleDeg: number): string {
  if (line.source === "survey") return "Подошва для ЛСП — нижняя бровка из чертежа";
  const reason = ANGLE_TOE_REASON[line.reason ?? ""];
  const tail = reason ? `: ${reason}` : "";
  if (faceAngleDeg >= 90) return `Подошва для ЛСП совпадает с бровкой — угол откоса не задан${tail}`;
  return `Подошва для ЛСП — по углу откоса ${ruNumber(90 - faceAngleDeg, 0)}° от вертикали${tail}`;
}

/** Предупреждение для сводки: откос из чертежа не учтён, ЛСП — по углу. */
export function toeLineWarning(line: ToeLine | null): string {
  if (line?.source !== "angle" || line.reason !== "survey_unmatched") return "";
  return "Откос из чертежа не учтён: нижний контур совпал с верхним, ЛСП считается по углу откоса — постройте контур заново.";
}
