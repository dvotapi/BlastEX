// Перенумерация скважин по правилу эшелонов (доработки 10.11.2026). Сервер
// (`POST /design/holes/renumber`) даёт соответствие «старый номер → новый»;
// здесь оно применяется ко всем ссылкам документа сразу (без каскада: номера
// могут переставляться). Скважины не двигаются. Список ссылок — как у
// `pruneLoadsAndNetwork` в `designReducer.ts`.
import { normalizeNetwork, type BlastDesign } from "../../types/design";

/** Производный id элемента сети с номером скважины: «det-5-08», «fire-5-08-d1». */
function derived(id: string, prefix: string, oldHole: string, newHole: string): string {
  const head = `${prefix}${oldHole}`;
  if (id === head || id.startsWith(`${head}-d`)) return `${prefix}${newHole}${id.slice(head.length)}`;
  return id;
}

export function renameHoleIds(document: BlastDesign, mapping: Record<string, string>): BlastDesign {
  if (!Object.keys(mapping).length) return document;
  const to = (id: string) => mapping[id] ?? id;
  const rekey = (values: Record<string, number>) =>
    Object.fromEntries(Object.entries(values).map(([id, value]) => [to(id), value]));
  const network = normalizeNetwork(document.network);
  return {
    ...document,
    holes: document.holes.map((hole) => ({ ...hole, id: to(hole.id) })),
    loads: document.loads.map((load) => ({ ...load, hole_id: to(load.hole_id) })),
    network: {
      ...network,
      starters: network.starters.map(to),
      connectors: network.connectors.map((c) => ({ ...c, from_hole: to(c.from_hole), to_hole: to(c.to_hole) })),
      downhole_delay_ms: rekey(network.downhole_delay_ms),
      electronic_times_ms: rekey(network.electronic_times_ms),
      detonators: network.detonators.map((item) => ({
        ...item,
        id: derived(item.id, "det-", item.hole_id, to(item.hole_id)),
        hole_id: to(item.hole_id),
        channel_id: derived(item.channel_id, "ch-", item.hole_id, to(item.hole_id)),
      })),
      surface_connectors: network.surface_connectors.map((item) => ({
        ...item,
        id: item.id === `sc-${item.from_hole}-${item.to_hole}` ? `sc-${to(item.from_hole)}-${to(item.to_hole)}` : item.id,
        from_hole: to(item.from_hole),
        to_hole: to(item.to_hole),
      })),
      downhole_connectors: network.downhole_connectors.map((item) => ({
        ...item, id: derived(item.id, "dh-", item.hole_id, to(item.hole_id)), hole_id: to(item.hole_id),
      })),
      detonating_cords: network.detonating_cords.map((cord) => ({ ...cord, hole_ids: cord.hole_ids.map(to) })),
      starter_items: network.starter_items.map((item) => ({
        ...item, id: derived(item.id, "st-", item.hole_id, to(item.hole_id)), hole_id: to(item.hole_id),
      })),
      electronic_channels: network.electronic_channels.map((item) => ({
        ...item, id: derived(item.id, "ch-", item.hole_id, to(item.hole_id)), hole_id: to(item.hole_id),
      })),
      firing_events: network.firing_events.map((item) => ({
        ...item, id: derived(item.id, "fire-", item.hole_id, to(item.hole_id)), hole_id: to(item.hole_id),
      })),
      selected_hole_ids: network.selected_hole_ids.map(to),
    },
    as_drilled_holes: document.as_drilled_holes.map((item) => ({ ...item, design_hole_id: to(item.design_hole_id) })),
    as_charged_holes: document.as_charged_holes.map((item) => ({ ...item, design_hole_id: to(item.design_hole_id) })),
    as_fired_holes: document.as_fired_holes.map((item) => ({
      ...item,
      design_hole_id: to(item.design_hole_id),
      detonator: item.detonator
        ? {
            ...item.detonator,
            id: derived(item.detonator.id, "det-", item.detonator.hole_id, to(item.detonator.hole_id)),
            hole_id: to(item.detonator.hole_id),
          }
        : item.detonator,
    })),
  };
}

/** Номера скважин в состоянии страницы (выделение, замер) — на новые. */
export function remapHoleIds(ids: Iterable<string>, mapping: Record<string, string>): string[] {
  return Array.from(ids, (id) => mapping[id] ?? id);
}

/** Номер одной скважины (инспектор, начатая связь) — на новый. */
export function remapHoleId(id: string | null, mapping: Record<string, string>): string | null {
  return id === null ? null : (mapping[id] ?? id);
}

/**
 * Параметры сетки для перенумерации — сохранённые с проектом. Параметры
 * вкладки «Сетка» могли поменять без перестроения; нет азимута рядов —
 * сервер находит его по самим скважинам.
 */
export function renumberParams(document: BlastDesign): Record<string, unknown> {
  return { ...(document.pattern_params ?? {}) };
}
