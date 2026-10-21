// Угол откоса уступа в формах вводится от вертикали (15° — откос 75° от
// горизонтали). Положе 60° от вертикали откос не бывает, а 90° дал бы угол от
// горизонтали 0° — сервер такой паспорт не примет.

export const FACE_ANGLE_FROM_VERTICAL_MAX_DEG = 60;

/** Угол откоса объекта по умолчанию от вертикали, ° (лист «Расчёт»). */
export const DEFAULT_FACE_ANGLE_FROM_VERTICAL_DEG = 15;

/** Угол от вертикали в пределах 0–60°. */
export function clampFaceAngleFromVertical(value: number): number {
  return Math.min(FACE_ANGLE_FROM_VERTICAL_MAX_DEG, Math.max(0, value));
}

/** Ввод поля угла: пусто или не число — прежний угол, иначе 0–60°. */
export function faceAngleFromVerticalInput(raw: string, previous: number): number {
  if (raw.trim() === "") return previous;
  const value = Number(raw);
  return Number.isFinite(value) ? clampFaceAngleFromVertical(value) : previous;
}

/**
 * Угол откоса (от горизонтали) блока после «Построить блок» из чертежа:
 * угол блока остаётся; 90° — умолчание сервера у паспорта без угла, а не
 * выбор пользователя, — такой блок получает угол объекта по умолчанию (15° от
 * вертикали). Иначе построенная подошва совпала бы с бровкой (спецификация
 * оптимизатора раскладки, «Съёмка с развалом»).
 */
export function faceAngleForImportedBlock(current: number | null | undefined): number {
  if (typeof current === "number" && Number.isFinite(current) && current > 0 && current < 90) return current;
  return 90 - DEFAULT_FACE_ANGLE_FROM_VERTICAL_DEG;
}
