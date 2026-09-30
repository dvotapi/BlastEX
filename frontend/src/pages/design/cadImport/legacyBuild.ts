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
