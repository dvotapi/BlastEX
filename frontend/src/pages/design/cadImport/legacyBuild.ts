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
  for (const entity of lines) {
    if (entity.role === "crest_top" || entity.role === "crest_bottom" || keep.includes(entity.handle)) chosen.add(entity);
  }
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

/**
 * Отрезки LINE одного слоя, склеенные в цепочки, — для построения по-старому.
 *
 * Прежний диалог склеивал их сам, а построение берёт одну линию: без склейки
 * бровка, начерченная отрезками, дала бы полоску из одного отрезка. Импорт
 * хранит отрезки как есть (у каждого свой handle), поэтому цепочки — только
 * здесь и только до шага «Контур» (PR 2 сшивает фрагменты на сервере).
 * `members` — handle отрезков каждой цепочки, по порядку.
 */
export function withLineChains(entities: CadEntity[]): { entities: CadEntity[]; members: Map<string, string[]> } {
  const byLayer = new Map<string, CadEntity[]>();
  for (const entity of entities) {
    if (entity.kind !== "LINE" || entity.points.length !== 2) continue;
    const list = byLayer.get(entity.layer);
    if (list) list.push(entity);
    else byLayer.set(entity.layer, [entity]);
  }

  const chains: CadEntity[] = [];
  const members = new Map<string, string[]>();
  for (const [layer, segments] of byLayer) {
    const pending = [...segments];
    let index = 0;
    while (pending.length) {
      const first = pending.shift()!;
      const parts = [first];
      let points: ChainPoint[] = [...first.points];
      let merged = true;
      while (merged) {
        merged = false;
        for (let at = 0; at < pending.length; at += 1) {
          const [a, b] = pending[at].points;
          const head = points[0];
          const tail = points[points.length - 1];
          if (same(tail, a)) points = [...points, b];
          else if (same(tail, b)) points = [...points, a];
          else if (same(head, b)) points = [a, ...points];
          else if (same(head, a)) points = [b, ...points];
          else continue;
          parts.push(pending[at]);
          pending.splice(at, 1);
          merged = true;
          break;
        }
      }
      if (parts.length < 2) continue;
      index += 1;
      const chain = chainOf(layer, index, parts, points);
      chains.push(chain);
      members.set(chain.handle, parts.map((part) => part.handle));
    }
  }
  return { entities: [...entities, ...chains], members };
}
