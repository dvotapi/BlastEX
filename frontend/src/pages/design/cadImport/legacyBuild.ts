// Построение блока «по-старому» — полосой между верхней и нижней бровкой —
// остаётся до шага «Контур» (TASK-013, PR 2). Здесь выбор пары линий по
// умолчанию: по ролям бровок, а без них — по отметкам, как в прежнем диалоге.
import type { CadEntity } from "../../../types/cad";

const meanZ = (entity: CadEntity) => (entity.z_min + entity.z_max) / 2;

function longest(entities: CadEntity[]): CadEntity | undefined {
  return [...entities].sort((a, b) => b.length_m - a.length_m)[0];
}

export function defaultBenchPair(entities: CadEntity[]): { crest: string; toe: string } {
  const lines = entities.filter((entity) => entity.geometry_type === "line" && entity.vertex_count >= 2);
  const crest = longest(lines.filter((entity) => entity.role === "crest_top"));
  const toe = longest(lines.filter((entity) => entity.role === "crest_bottom"));
  if (crest && toe) return { crest: crest.handle, toe: toe.handle };

  // Служебные линии на Z = 0 (рамки, оси) бровками быть не могут.
  const candidates = [...lines]
    .filter((entity) => entity.z_kind !== "zero")
    .sort((a, b) => b.length_m - a.length_m)
    .slice(0, 6);
  if (!candidates.length) return { crest: "", toe: "" };
  const top = candidates.reduce((best, entity) => (meanZ(entity) > meanZ(best) ? entity : best));
  const below = candidates.filter((entity) => entity !== top && meanZ(entity) < meanZ(top));
  return { crest: top.handle, toe: below[0]?.handle ?? "" };
}

/** Сколько самых длинных линий предлагать в «Верх» и «Низ» помимо бровок. */
const LONGEST_CANDIDATES = 100;

/**
 * Линии для списков «Верх» и «Низ»: бровки по ролям, уже выбранные и сотня
 * самых длинных. На чертеже карьера линий десятки тысяч — список из них всех
 * не выбрать глазами и дорого перерисовывать.
 */
export function benchCandidates(entities: CadEntity[], keep: string[]): CadEntity[] {
  const lines = entities.filter((entity) => entity.geometry_type === "line");
  const sorted = [...lines].sort((a, b) => b.length_m - a.length_m);
  const chosen = new Set(sorted.slice(0, LONGEST_CANDIDATES));
  // Бровок по ролям тоже не больше сотни самых длинных: несвязных фрагментов
  // бывают тысячи, а список из тысяч вариантов не выбрать глазами.
  const crests = sorted.filter((entity) => entity.role === "crest_top" || entity.role === "crest_bottom");
  for (const entity of crests.slice(0, LONGEST_CANDIDATES)) chosen.add(entity);
  const kept = new Set(keep);
  for (const entity of lines) if (kept.has(entity.handle)) chosen.add(entity);
  return sorted.filter((entity) => chosen.has(entity));
}

/** Концы отрезков ближе этого — один узел (съёмка приходит с округлением). */
const CHAIN_TOLERANCE_M = 0.01;

type ChainPoint = CadEntity["points"][number];

const same = (a: ChainPoint, b: ChainPoint) =>
  Math.abs(a[0] - b[0]) <= CHAIN_TOLERANCE_M &&
  Math.abs(a[1] - b[1]) <= CHAIN_TOLERANCE_M &&
  Math.abs(a[2] - b[2]) <= CHAIN_TOLERANCE_M;

function chainOf(layer: string, index: number, parts: CadEntity[], points: ChainPoint[]): CadEntity {
  const zs = points.map((point) => point[2]);
  const zMin = Math.min(...zs);
  const zMax = Math.max(...zs);
  return {
    ...parts[0],
    handle: `chain:${layer}:${index}`,
    points,
    closed: false,
    closed_by_gap: false,
    vertex_count: points.length,
    length_m: parts.reduce((total, part) => total + part.length_m, 0),
    area_m2: 0,
    z_kind: zs.every((z) => Math.abs(z) <= 0.001) ? "zero" : zMax - zMin <= 0.005 ? "const" : "variable",
    z_min: zMin,
    z_max: zMax,
  };
}

/** Ключ ячейки индекса концов: сосед ищется в своей и восьми соседних ячейках. */
function cell(x: number, y: number): [number, number] {
  return [Math.floor(x / CHAIN_TOLERANCE_M), Math.floor(y / CHAIN_TOLERANCE_M)];
}

/**
 * Отрезки LINE одного слоя, склеенные в цепочки, — для построения по-старому.
 *
 * Прежний диалог склеивал их сам, а построение берёт одну линию: без склейки
 * бровка, начерченная отрезками, дала бы полоску из одного отрезка. Импорт
 * хранит отрезки как есть (у каждого свой handle), поэтому цепочки — только
 * здесь и только до шага «Контур» (PR 2 сшивает фрагменты на сервере).
 *
 * Склеиваются только отрезки одного слоя с одной ролью: отросток, выключенный
 * вручную, в цепочку бровки не попадёт. Концы ищутся по индексу ячеек, цепочка
 * растёт с обоих концов без копирования — десятки тысяч отрезков не заморозят
 * окно. `members` — handle отрезков каждой цепочки в порядке склейки.
 *
 * Отрезки, вошедшие в цепочку, в `entities` заменены ею: в «Верх» и «Низ»
 * предлагается собранная бровка, а не тысяча её фрагментов.
 */
export function withLineChains(entities: CadEntity[]): { entities: CadEntity[]; members: Map<string, string[]> } {
  const groups = new Map<string, CadEntity[]>();
  for (const entity of entities) {
    if (entity.kind !== "LINE" || entity.points.length !== 2) continue;
    const key = `${entity.layer}\u0000${entity.role}`;
    const list = groups.get(key);
    if (list) list.push(entity);
    else groups.set(key, [entity]);
  }

  const chains: CadEntity[] = [];
  const members = new Map<string, string[]>();
  const counters = new Map<string, number>();
  for (const segments of groups.values()) {
    const layer = segments[0].layer;
    const index = new Map<string, number[]>();
    const register = (point: ChainPoint, at: number) => {
      const [cx, cy] = cell(point[0], point[1]);
      const key = `${cx}:${cy}`;
      const list = index.get(key);
      if (list) list.push(at);
      else index.set(key, [at]);
    };
    segments.forEach((segment, at) => {
      register(segment.points[0], at);
      register(segment.points[1], at);
    });
    const used = new Uint8Array(segments.length);
    const next = (point: ChainPoint): [number, ChainPoint] | null => {
      const [cx, cy] = cell(point[0], point[1]);
      for (let dx = -1; dx <= 1; dx += 1) {
        for (let dy = -1; dy <= 1; dy += 1) {
          for (const at of index.get(`${cx + dx}:${cy + dy}`) ?? []) {
            if (used[at]) continue;
            const [a, b] = segments[at].points;
            if (same(point, a)) return [at, b];
            if (same(point, b)) return [at, a];
          }
        }
      }
      return null;
    };

    for (let start = 0; start < segments.length; start += 1) {
      if (used[start]) continue;
      used[start] = 1;
      const order = [start];
      const tail: ChainPoint[] = [...segments[start].points];
      const head: ChainPoint[] = []; // растёт от начала цепочки наружу
      for (let found = next(tail[tail.length - 1]); found; found = next(tail[tail.length - 1])) {
        used[found[0]] = 1;
        order.push(found[0]);
        tail.push(found[1]);
      }
      for (let found = next(tail[0]); found; found = next(head.length ? head[head.length - 1] : tail[0])) {
        used[found[0]] = 1;
        order.push(found[0]);
        head.push(found[1]);
      }
      if (order.length < 2) continue;
      const parts = order.map((at) => segments[at]);
      const number = (counters.get(layer) ?? 0) + 1;
      counters.set(layer, number);
      const chain = chainOf(layer, number, parts, head.reverse().concat(tail));
      chains.push(chain);
      members.set(chain.handle, parts.map((part) => part.handle));
    }
  }
  const chained = new Set<string>();
  for (const handles of members.values()) for (const handle of handles) chained.add(handle);
  return { entities: [...entities.filter((entity) => !chained.has(entity.handle)), ...chains], members };
}
