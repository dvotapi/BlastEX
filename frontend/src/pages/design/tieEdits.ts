// Правка коммутации на плане (TASK-017, PR 4): чистые функции над сетью.
//
// Каждая функция — одна правка: страница отдаёт её результат одним
// `SET_NETWORK`, то есть одной записью отмены (протяжка цепочки — тоже).
// Изменённая сеть помечается правленой (`retie.ts::markNetworkEdited`): после
// неё сдвиг скважин сеть сам не пересчитает и правки не сотрёт.
//
// Правила (решения владельца по TASK-017): у скважины одна входящая связь —
// новая заменяет прежнюю; связь, замыкающая путь на себя (цикл), не
// создаётся. Те же правила — у разворота и перецепки конца.
import {
  networkTies,
  type DownholeConnector,
  type InitiationNetwork,
  type Starter,
  type SurfaceConnector,
} from "../../types/design";
import { markNetworkEdited } from "./retie";

export type TieCycle = { from: string; to: string };

export type TieEditResult = {
  /** Сеть после правки; правки не было — прежний объект. */
  network: InitiationNetwork;
  /** Связи, которые новая связь заменила у своей цели. */
  replaced: SurfaceConnector[];
  /** Связи, которые не поставлены: цель уже срабатывает раньше источника. */
  cycles: TieCycle[];
  changed: boolean;
};

function unchanged(network: InitiationNetwork, cycles: TieCycle[] = []): TieEditResult {
  return { network, replaced: [], cycles, changed: false };
}

function connectorKind(system: InitiationNetwork["system"]): string {
  if (system === "detcord") return "ds_relay";
  if (system === "electronic") return "electronic";
  return "surface_nsi";
}

/** Сеть со связями `ties`: обе формы (v2 и прежняя `connectors`) — одинаковые. */
function withTies(network: InitiationNetwork, ties: SurfaceConnector[]): InitiationNetwork {
  return {
    ...network,
    surface_connectors: ties,
    connectors: ties.map((item) => ({ from_hole: item.from_hole, to_hole: item.to_hole, delay_ms: item.delay_ms, kind: item.kind })),
  };
}

function starterItems(network: InitiationNetwork): Starter[] {
  return network.starter_items?.length
    ? [...network.starter_items]
    : (network.starters ?? []).map((id) => ({ id: `st-${id}`, hole_id: id, delay_ms: 0, kind: "starter" }));
}

function withStarters(network: InitiationNetwork, items: Starter[]): InitiationNetwork {
  return { ...network, starter_items: items, starters: items.map((item) => item.hole_id) };
}

/** От `start` по связям достижима `target` (`start` срабатывает раньше). */
function reaches(ties: SurfaceConnector[], start: string, target: string): boolean {
  if (start === target) return true;
  const out = new Map<string, string[]>();
  for (const item of ties) {
    const list = out.get(item.from_hole);
    if (list) list.push(item.to_hole);
    else out.set(item.from_hole, [item.to_hole]);
  }
  const seen = new Set([start]);
  const stack = [start];
  while (stack.length) {
    for (const next of out.get(stack.pop()!) ?? []) {
      if (next === target) return true;
      if (!seen.has(next)) {
        seen.add(next);
        stack.push(next);
      }
    }
  }
  return false;
}

/**
 * Ставит связь `from → to` в список: прежние входящие `to` уходят (в
 * `replaced` — от другой скважины). Цикл — `null`.
 */
function placeTie(
  ties: SurfaceConnector[],
  tie: SurfaceConnector,
  replaced: SurfaceConnector[],
): SurfaceConnector[] | null {
  const rest = ties.filter((item) => item.to_hole !== tie.to_hole);
  if (reaches(rest, tie.to_hole, tie.from_hole)) return null;
  for (const item of ties) {
    if (item.to_hole === tie.to_hole && item.from_hole !== tie.from_hole) replaced.push(item);
  }
  return [...rest, tie];
}

function sameTies(a: SurfaceConnector[], b: SurfaceConnector[]): boolean {
  if (a.length !== b.length) return false;
  const key = (item: SurfaceConnector) => `${item.id}|${item.from_hole}|${item.to_hole}|${item.delay_ms}|${item.kind}`;
  const left = a.map(key).sort();
  const right = b.map(key).sort();
  return left.every((value, index) => value === right[index]);
}

function finish(
  network: InitiationNetwork,
  next: InitiationNetwork,
  ties: SurfaceConnector[],
  replaced: SurfaceConnector[],
  cycles: TieCycle[],
): TieEditResult {
  if (sameTies(networkTies(network), ties) && next.starters.join("\n") === network.starters.join("\n")) {
    return unchanged(network, cycles);
  }
  return { network: markNetworkEdited(withTies(next, ties)), replaced, cycles, changed: true };
}

/**
 * Связи по пути `path` (протяжка через скважины или две скважины кликом):
 * каждая следующая скважина — от предыдущей, ступень `delayMs`. Отрезок,
 * замыкающий цикл, пропускается. Исток связи без входа и не стартовая —
 * становится стартовой (иначе новая цепочка осталась бы без сигнала).
 */
export function addTies(network: InitiationNetwork, path: string[], delayMs: number): TieEditResult {
  let ties = networkTies(network);
  const replaced: SurfaceConnector[] = [];
  const cycles: TieCycle[] = [];
  const kind = connectorKind(network.system);
  const sources: string[] = [];
  for (let i = 0; i + 1 < path.length; i += 1) {
    const from = path[i];
    const to = path[i + 1];
    if (!from || !to || from === to) continue;
    const existing = ties.find((item) => item.from_hole === from && item.to_hole === to);
    const tie: SurfaceConnector = {
      id: `sc-${from}-${to}`,
      from_hole: from,
      to_hole: to,
      delay_ms: delayMs,
      kind: existing?.kind || kind,
      product: existing?.product ?? "",
    };
    const placed = placeTie(ties, tie, replaced);
    if (!placed) {
      cycles.push({ from, to });
      continue;
    }
    ties = placed;
    sources.push(from);
  }
  let items = starterItems(network);
  for (const source of sources) {
    if (!items.some((item) => item.hole_id === source) && !ties.some((item) => item.to_hole === source)) {
      items = [...items, { id: `st-${source}`, hole_id: source, delay_ms: 0, kind: "starter" }];
    }
  }
  const next = items.length === starterItems(network).length ? network : withStarters(network, items);
  return finish(network, next, ties, replaced, cycles);
}

/** Ступень `delayMs` выбранным связям. */
export function setTiesDelay(network: InitiationNetwork, ids: string[], delayMs: number): TieEditResult {
  const chosen = new Set(ids);
  const ties = networkTies(network).map((item) => (chosen.has(item.id) ? { ...item, delay_ms: delayMs } : item));
  return finish(network, network, ties, [], []);
}

export function removeTies(network: InitiationNetwork, ids: string[]): TieEditResult {
  const chosen = new Set(ids);
  const ties = networkTies(network).filter((item) => !chosen.has(item.id));
  return finish(network, network, ties, [], []);
}

/** Связь вместо `old`: снять прежнюю и поставить новую по правилам. */
function replaceTie(network: InitiationNetwork, old: SurfaceConnector, from: string, to: string): TieEditResult {
  if (from === to || (from === old.from_hole && to === old.to_hole)) return unchanged(network);
  const rest = networkTies(network).filter((item) => item.id !== old.id);
  const replaced: SurfaceConnector[] = [];
  const placed = placeTie(rest, { ...old, id: `sc-${from}-${to}`, from_hole: from, to_hole: to }, replaced);
  if (!placed) return unchanged(network, [{ from, to }]);
  return finish(network, network, placed, replaced, []);
}

/** «Развернуть направление»: `a → b` становится `b → a`. */
export function reverseTie(network: InitiationNetwork, id: string): TieEditResult {
  const old = networkTies(network).find((item) => item.id === id);
  return old ? replaceTie(network, old, old.to_hole, old.from_hole) : unchanged(network);
}

/** Перецепка конца связи (`from` — начало, `to` — конец) на скважину `holeId`. */
export function reconnectTie(network: InitiationNetwork, id: string, end: "from" | "to", holeId: string): TieEditResult {
  const old = networkTies(network).find((item) => item.id === id);
  if (!old) return unchanged(network);
  if (end === "to") return replaceTie(network, old, old.from_hole, holeId);
  const result = replaceTie(network, old, holeId, old.to_hole);
  // Новое начало без входа и не стартовая — стартовая, как у новой связи (`addTies`).
  if (!result.changed) return result;
  const items = starterItems(result.network);
  if (items.some((item) => item.hole_id === holeId) || networkTies(result.network).some((item) => item.to_hole === holeId)) return result;
  return { ...result, network: withStarters(result.network, [...items, { id: `st-${holeId}`, hole_id: holeId, delay_ms: 0, kind: "starter" }]) };
}

/** «Стартер»: поставить или снять стартовую у скважины. */
export function toggleStarter(network: InitiationNetwork, holeId: string): TieEditResult {
  const items = starterItems(network);
  const next = items.some((item) => item.hole_id === holeId)
    ? items.filter((item) => item.hole_id !== holeId)
    : [...items, { id: `st-${holeId}`, hole_id: holeId, delay_ms: 0, kind: "starter" }];
  return { network: markNetworkEdited(withStarters(network, next)), replaced: [], cycles: [], changed: true };
}

/**
 * «В скважине»: замедление внутрискважинного детонатора. Пишется в карту
 * `downhole_delay_ms`, в соединитель скважины (`downhole_connectors`, без деки
 * и боевика — его читает расчёт времён первым) и в скважинный детонатор, если он есть.
 */
export function setDownholeDelay(network: InitiationNetwork, holeIds: string[], delayMs: number): TieEditResult {
  const chosen = new Set(holeIds);
  const holeLevel = (item: { hole_id: string; deck_index: number | null; primer_index: number | null }) =>
    chosen.has(item.hole_id) && item.deck_index == null && item.primer_index == null;
  const map = network.downhole_delay_ms ?? {};
  const connectors = network.downhole_connectors ?? [];
  const detonators = network.detonators ?? [];
  const changed =
    holeIds.some((id) => map[id] !== delayMs || !connectors.some((item) => holeLevel(item) && item.hole_id === id))
    || connectors.some((item) => holeLevel(item) && item.delay_ms !== delayMs)
    || detonators.some((item) => holeLevel(item) && item.delay_ms !== delayMs);
  if (!changed) return unchanged(network);
  const kind = network.system === "electronic" ? "electronic" : "downhole_nsi";
  const nextConnectors: DownholeConnector[] = connectors.map((item) => (holeLevel(item) ? { ...item, delay_ms: delayMs } : item));
  for (const id of holeIds) {
    if (!nextConnectors.some((item) => item.hole_id === id && item.deck_index == null && item.primer_index == null)) {
      nextConnectors.push({ id: `dh-${id}`, hole_id: id, delay_ms: delayMs, kind, deck_index: null, primer_index: null, product: "" });
    }
  }
  return {
    network: markNetworkEdited({
      ...network,
      downhole_delay_ms: { ...map, ...Object.fromEntries(holeIds.map((id) => [id, delayMs])) },
      downhole_connectors: nextConnectors,
      detonators: detonators.map((item) => (holeLevel(item) ? { ...item, delay_ms: delayMs } : item)),
    }),
    replaced: [],
    cycles: [],
    changed: true,
  };
}

/** Подсказка после правки: заменённые связи и не поставленные из-за цикла. */
export function tieEditNotice(result: TieEditResult): string {
  const parts: string[] = [];
  if (result.replaced.length === 1) {
    const [item] = result.replaced;
    parts.push(`Связь ${item.from_hole} → ${item.to_hole} заменена`);
  } else if (result.replaced.length > 1) {
    parts.push(`Заменено связей: ${result.replaced.length}`);
  }
  if (result.cycles.length) parts.push(`Цикл: скважина ${result.cycles[0].to} уже срабатывает раньше`);
  return parts.join(" · ");
}

/** Число связей каждой ступени (легенда палитры). */
export function stepCounts(network: InitiationNetwork): Map<number, number> {
  const counts = new Map<number, number>();
  for (const item of networkTies(network)) counts.set(item.delay_ms, (counts.get(item.delay_ms) ?? 0) + 1);
  return counts;
}
