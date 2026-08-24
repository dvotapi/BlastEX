// Экранные ↔ мировые координаты для плана блока (SVG-редактор). Только
// интерактивная геометрия (панорама/зум/попадание курсором) — вся предметная
// математика (сетка, объём, тайминг) считается на сервере.

export type Vec2 = { x: number; y: number };

export type Camera = { x: number; y: number; scale: number };

export type Viewport = { width: number; height: number };

export function worldToScreen(camera: Camera, viewport: Viewport, point: Vec2): Vec2 {
  return {
    x: viewport.width / 2 + (point.x - camera.x) * camera.scale,
    y: viewport.height / 2 - (point.y - camera.y) * camera.scale,
  };
}

export function screenToWorld(camera: Camera, viewport: Viewport, point: Vec2): Vec2 {
  return {
    x: camera.x + (point.x - viewport.width / 2) / camera.scale,
    y: camera.y - (point.y - viewport.height / 2) / camera.scale,
  };
}

export function distance(a: Vec2, b: Vec2): number {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

export function pointInCircle(p: Vec2, center: Vec2, radius: number): boolean {
  return distance(p, center) <= radius;
}

export function rectFromCorners(a: Vec2, b: Vec2): { minX: number; minY: number; maxX: number; maxY: number } {
  return {
    minX: Math.min(a.x, b.x),
    minY: Math.min(a.y, b.y),
    maxX: Math.max(a.x, b.x),
    maxY: Math.max(a.y, b.y),
  };
}

export function rectContains(rect: { minX: number; minY: number; maxX: number; maxY: number }, p: Vec2): boolean {
  return p.x >= rect.minX && p.x <= rect.maxX && p.y >= rect.minY && p.y <= rect.maxY;
}

// Пределы масштаба: от обзора карьерного блока целиком до отдельной скважины.
export const MIN_SCALE = 0.05;
export const MAX_SCALE = 400;

export function zoomAt(
  camera: Camera,
  viewport: Viewport,
  screenPoint: Vec2,
  factor: number,
  minScale = MIN_SCALE,
  maxScale = MAX_SCALE,
): Camera {
  const worldBefore = screenToWorld(camera, viewport, screenPoint);
  const nextScale = Math.min(maxScale, Math.max(minScale, camera.scale * factor));
  const nextCamera = { ...camera, scale: nextScale };
  const worldAfter = screenToWorld(nextCamera, viewport, screenPoint);
  return {
    x: nextCamera.x - (worldAfter.x - worldBefore.x),
    y: nextCamera.y - (worldAfter.y - worldBefore.y),
    scale: nextScale,
  };
}

export function snap(value: number, step: number): number {
  if (step <= 0) return value;
  return Math.round(value / step) * step;
}

export type Point3 = { x: number; y: number; z: number };

/**
 * Зеркалит design/geometry.py::hole_from_collar — только для мгновенного
 * визуального размещения вручную добавленной скважины. Источник истины
 * остаётся на сервере: при следующей генерации сетки или пересчёте забой
 * скважины вычисляется заново бэкендом.
 */
export function holeFromCollar(collar: Point3, depthM: number, angleDeg: number, azimuthDeg: number): Point3 {
  const angleRad = (angleDeg * Math.PI) / 180;
  const azimuthRad = (azimuthDeg * Math.PI) / 180;
  const horizontal = depthM * Math.sin(angleRad);
  const vertical = depthM * Math.cos(angleRad);
  return {
    x: collar.x + horizontal * Math.sin(azimuthRad),
    y: collar.y + horizontal * Math.cos(azimuthRad),
    z: collar.z - vertical,
  };
}

/**
 * Зеркалит design/geometry.py::local_basis — направление вдоль ряда, только
 * для проекции скважин на ось разреза по ряду на клиенте. Не используется
 * для раскладки сетки (та считается на сервере).
 */
export function localBasis(rowAzimuthDeg: number): { rowDir: Vec2; advanceDir: Vec2 } {
  const az = (rowAzimuthDeg * Math.PI) / 180;
  const rowDir = { x: Math.sin(az), y: Math.cos(az) };
  const advanceDir = { x: rowDir.y, y: -rowDir.x };
  return { rowDir, advanceDir };
}

export function holeLength(collar: Point3, toe: Point3): number {
  return Math.hypot(toe.x - collar.x, toe.y - collar.y, toe.z - collar.z);
}

export type Bounds = { minX: number; minY: number; maxX: number; maxY: number };

/** Габариты набора точек; null — если точек нет. */
export function boundsOf(points: Vec2[]): Bounds | null {
  if (!points.length) return null;
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const p of points) {
    if (p.x < minX) minX = p.x;
    if (p.y < minY) minY = p.y;
    if (p.x > maxX) maxX = p.x;
    if (p.y > maxY) maxY = p.y;
  }
  return { minX, minY, maxX, maxY };
}

/**
 * Камера, при которой габариты целиком попадают во вьюпорт с полями.
 * Используется кнопкой «По размеру» и автоподгонкой после раскладки сетки.
 */
export function fitCamera(
  bounds: Bounds,
  viewport: Viewport,
  padding = 0.12,
  fallbackScale = 6,
  minScale = MIN_SCALE,
  maxScale = MAX_SCALE,
): Camera {
  const center = { x: (bounds.minX + bounds.maxX) / 2, y: (bounds.minY + bounds.maxY) / 2 };
  const width = Math.max(bounds.maxX - bounds.minX, 0);
  const height = Math.max(bounds.maxY - bounds.minY, 0);
  const usableW = Math.max(viewport.width * (1 - padding * 2), 1);
  const usableH = Math.max(viewport.height * (1 - padding * 2), 1);
  const scaleX = width > 1e-6 ? usableW / width : Infinity;
  const scaleY = height > 1e-6 ? usableH / height : Infinity;
  const raw = Math.min(scaleX, scaleY);
  const scale = Number.isFinite(raw) ? raw : fallbackScale;
  return { x: center.x, y: center.y, scale: Math.min(maxScale, Math.max(minScale, scale)) };
}

/** Сдвиг камеры на заданное число экранных пикселей. */
export function panCameraByScreen(camera: Camera, dxPx: number, dyPx: number): Camera {
  return { ...camera, x: camera.x + dxPx / camera.scale, y: camera.y - dyPx / camera.scale };
}

/** Ближайший «круглый» шаг (1·10ⁿ, 2·10ⁿ, 5·10ⁿ) не меньше запрошенного. */
export function niceStep(rough: number): number {
  if (!Number.isFinite(rough) || rough <= 0) return 1;
  const exponent = Math.floor(Math.log10(rough));
  const base = 10 ** exponent;
  const normalized = rough / base;
  const factor = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
  return factor * base;
}

/** Мировые границы, видимые во вьюпорте при текущей камере. */
export function visibleBounds(camera: Camera, viewport: Viewport): Bounds {
  const topLeft = screenToWorld(camera, viewport, { x: 0, y: 0 });
  const bottomRight = screenToWorld(camera, viewport, { x: viewport.width, y: viewport.height });
  return {
    minX: Math.min(topLeft.x, bottomRight.x),
    maxX: Math.max(topLeft.x, bottomRight.x),
    minY: Math.min(topLeft.y, bottomRight.y),
    maxY: Math.max(topLeft.y, bottomRight.y),
  };
}

/** Проекция точки на отрезок и расстояние до неё — попадание курсором по ребру. */
export function projectOnSegment(p: Vec2, a: Vec2, b: Vec2): { point: Vec2; distance: number; t: number } {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const lengthSq = dx * dx + dy * dy;
  if (lengthSq < 1e-9) return { point: a, distance: distance(p, a), t: 0 };
  const t = Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / lengthSq));
  const point = { x: a.x + t * dx, y: a.y + t * dy };
  return { point, distance: distance(p, point), t };
}
