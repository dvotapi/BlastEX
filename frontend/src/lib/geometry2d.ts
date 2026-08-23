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

export function zoomAt(camera: Camera, viewport: Viewport, screenPoint: Vec2, factor: number, minScale = 0.5, maxScale = 200): Camera {
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

/** Mirrors design/geometry.py::angle_azimuth — collar/toe → inclination and dip azimuth. */
export function angleAzimuth(collar: Point3, toe: Point3): { angleDeg: number; azimuthDeg: number } {
  const horizontal = Math.hypot(toe.x - collar.x, toe.y - collar.y);
  const vertical = collar.z - toe.z;
  const angleDeg = horizontal || vertical ? (Math.atan2(horizontal, vertical) * 180) / Math.PI : 0;
  const dx = toe.x - collar.x;
  const dy = toe.y - collar.y;
  const azimuthDeg = dx || dy ? (((Math.atan2(dx, dy) * 180) / Math.PI) + 360) % 360 : 0;
  return { angleDeg, azimuthDeg };
}
