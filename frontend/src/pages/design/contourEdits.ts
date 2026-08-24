// Правка вершин контура на плане. Открытые откосы (`free_faces`) хранятся
// парами индексов вершин, поэтому вставка и удаление точки обязаны
// переиндексировать их — иначе пометки откосов «сползают» на соседние рёбра.
import type { Point3 } from "../../types/design";

export type ContourEdit = { vertices: Point3[]; freeFaces: number[][] };

function normalize(freeFaces: number[][], total: number): number[][] {
  const seen = new Set<string>();
  const result: number[][] = [];
  for (const face of freeFaces) {
    const [a, b] = face;
    if (a < 0 || b < 0 || a >= total || b >= total || a === b) continue;
    const key = `${a}-${b}`;
    if (seen.has(key)) continue;
    seen.add(key);
    result.push([a, b]);
  }
  return result;
}

/** Удаляет вершины по индексам, сохраняя пометки откосов на уцелевших рёбрах. */
export function removeContourVertices(
  vertices: Point3[],
  freeFaces: number[][],
  removed: Iterable<number>,
): ContourEdit {
  const drop = new Set(removed);
  if (!drop.size) return { vertices, freeFaces };

  const indexMap = new Map<number, number>();
  const nextVertices: Point3[] = [];
  vertices.forEach((vertex, index) => {
    if (drop.has(index)) return;
    indexMap.set(index, nextVertices.length);
    nextVertices.push(vertex);
  });

  const total = vertices.length;
  const nextFaces: number[][] = [];
  for (const [a, b] of freeFaces) {
    // Ребро исчезает вместе с любой из своих вершин: смежные рёбра сливаются
    // в одно, и переносить на него пометку откоса было бы догадкой.
    if (b !== (a + 1) % total) continue;
    const mappedA = indexMap.get(a);
    const mappedB = indexMap.get(b);
    if (mappedA === undefined || mappedB === undefined) continue;
    nextFaces.push([mappedA, mappedB]);
  }
  return { vertices: nextVertices, freeFaces: normalize(nextFaces, nextVertices.length) };
}

/**
 * Вставляет вершину в разрыв ребра `edgeIndex` (между вершинами edgeIndex и
 * edgeIndex+1). Обе половины разрезанного ребра наследуют признак откоса.
 */
export function insertContourVertex(
  vertices: Point3[],
  freeFaces: number[][],
  edgeIndex: number,
  vertex: Point3,
): ContourEdit {
  const total = vertices.length;
  if (total < 2 || edgeIndex < 0 || edgeIndex >= total) {
    return { vertices: [...vertices, vertex], freeFaces };
  }
  const insertAt = edgeIndex + 1;
  const nextVertices = [...vertices.slice(0, insertAt), vertex, ...vertices.slice(insertAt)];
  const shift = (index: number) => (index >= insertAt ? index + 1 : index);

  const nextFaces: number[][] = [];
  for (const [a, b] of freeFaces) {
    if (a === edgeIndex && b === (edgeIndex + 1) % total) {
      nextFaces.push([a, insertAt], [insertAt, shift(b)]);
      continue;
    }
    nextFaces.push([shift(a), shift(b)]);
  }
  return { vertices: nextVertices, freeFaces: normalize(nextFaces, nextVertices.length) };
}
