// Угол откоса уступа в формах вводится от вертикали (15° — откос 75° от
// горизонтали). Положе 60° от вертикали откос не бывает, а 90° дал бы угол от
// горизонтали 0° — сервер такой паспорт не примет.

export const FACE_ANGLE_FROM_VERTICAL_MAX_DEG = 60;

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
