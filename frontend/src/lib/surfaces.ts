import type { Point3, SurfaceModel, SurfaceSet, TIN } from "../types/design";

const EPS = 1e-12;
const LOCATE_EPS = 1e-9;

export function elevationAt(tin: TIN | undefined | null, x: number, y: number): number | null {
  if (!tin?.triangles?.length || !tin.vertices?.length) return null;
  for (const tri of tin.triangles) {
    if (tri.length < 3) continue;
    const a = tin.vertices[tri[0]];
    const b = tin.vertices[tri[1]];
    const c = tin.vertices[tri[2]];
    if (!a || !b || !c) continue;
    const z = barycentricZ(a, b, c, x, y);
    if (z !== null) return z;
  }
  return null;
}

export function surfaceElevation(surface: SurfaceModel | null | undefined, x: number, y: number): number | null {
  return surface ? elevationAt(surface.tin, x, y) : null;
}

export function collarZFromSurfaces(surfaces: SurfaceSet | undefined, x: number, y: number, fallbackZ: number): number {
  const z = surfaceElevation(surfaces?.top, x, y);
  return z === null ? fallbackZ : z;
}

function barycentricZ(a: Point3, b: Point3, c: Point3, x: number, y: number): number | null {
  const v0x = c.x - a.x;
  const v0y = c.y - a.y;
  const v1x = b.x - a.x;
  const v1y = b.y - a.y;
  const v2x = x - a.x;
  const v2y = y - a.y;
  const dot00 = v0x * v0x + v0y * v0y;
  const dot01 = v0x * v1x + v0y * v1y;
  const dot02 = v0x * v2x + v0y * v2y;
  const dot11 = v1x * v1x + v1y * v1y;
  const dot12 = v1x * v2x + v1y * v2y;
  const denom = dot00 * dot11 - dot01 * dot01;
  if (Math.abs(denom) < EPS) return null;
  const u = (dot11 * dot02 - dot01 * dot12) / denom;
  const v = (dot00 * dot12 - dot01 * dot02) / denom;
  if (u < -LOCATE_EPS || v < -LOCATE_EPS || u + v > 1 + LOCATE_EPS) return null;
  const w = 1 - u - v;
  return a.z * w + b.z * v + c.z * u;
}
