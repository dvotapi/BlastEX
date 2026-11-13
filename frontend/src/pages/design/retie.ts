// Пересчёт коммутации после сдвига скважин (TASK-017, PR 3).
//
// Построитель сети пишет в `timing_params` полный набор параметров
// повторного построения и `origin = "template"` (`design/timing.py::
// template_timing_params`); ручная правка связей ставит `origin = "edited"`.
// Сдвиг скважин ставит в непустую сеть пометку `geometry_stale`: сеть
// построена для прежних устьев. Пересчёт — тот же `POST /design/tie/generate`
// с параметрами из сети (`retieRequest` — порт `design/timing.py::retie_params`).
import { networkTies, SCHEME_TYPES, type InitiationNetwork, type SchemeType } from "../../types/design";

export type NetworkOrigin = "template" | "edited";

export const GEOMETRY_STALE_KEY = "geometry_stale";

export const GEOMETRY_STALE_TEXT = "Скважины сдвинуты после построения коммутации";
export const RETIE_INCOMPLETE_HINT =
  "Сеть построена до сохранения параметров схемы — постройте её заново во вкладке „Коммутация“";
export const RETIE_EDITED_CONFIRM = "Ручные правки коммутации будут потеряны. Пересчитать коммутацию?";

// Порядок «по выбору» — поле сети `selected_hole_ids` (его переименовывает
// перенумерация), а не копия в `timing_params`.
const SERVICE_KEYS: ReadonlySet<string> = new Set(["scheme", "origin", GEOMETRY_STALE_KEY, "selected_hole_ids"]);

/** Происхождение сети; нет ключа (сеть до PR 3) — правленая: автопересчёта нет. */
export function networkOrigin(network: InitiationNetwork): NetworkOrigin {
  return network.timing_params?.origin === "template" ? "template" : "edited";
}

/** Ручная правка связей: `origin` → «edited». Сеть без ключа «полной» от правки не становится. */
export function markNetworkEdited(network: InitiationNetwork): InitiationNetwork {
  const timing = network.timing_params ?? {};
  if (!("origin" in timing) || timing.origin === "edited") return network;
  return { ...network, timing_params: { ...timing, origin: "edited" } };
}

/** Схема и параметры повторного построения; параметров не хватает — null. */
export function retieRequest(network: InitiationNetwork): { scheme: SchemeType; params: Record<string, unknown> } | null {
  const timing = network.timing_params ?? {};
  if (!("origin" in timing) || typeof timing.scheme !== "string" || !SCHEME_TYPES.has(timing.scheme)) return null;
  const params = Object.fromEntries(Object.entries(timing).filter(([key]) => !SERVICE_KEYS.has(key)));
  const selected = network.selected_hole_ids?.length ? { selected_hole_ids: [...network.selected_hole_ids] } : {};
  return { scheme: timing.scheme as SchemeType, params: { ...params, system: network.system, ...selected } };
}

/** В сети нет ни стартовых, ни связей, ни электронных времён. */
export function isNetworkEmpty(network: InitiationNetwork): boolean {
  return !(
    network.starters?.length
    || network.starter_items?.length
    || network.connectors?.length
    || network.surface_connectors?.length
    || Object.keys(network.electronic_times_ms ?? {}).length
    || network.electronic_channels?.length
  );
}

export function isGeometryStale(network: InitiationNetwork): boolean {
  return network.timing_params?.[GEOMETRY_STALE_KEY] === true;
}

export function markGeometryStale(network: InitiationNetwork): InitiationNetwork {
  if (isGeometryStale(network)) return network;
  return { ...network, timing_params: { ...(network.timing_params ?? {}), [GEOMETRY_STALE_KEY]: true } };
}

export type RetieSummary = { changedTies: number; cutChanged: boolean };

function incoming(network: InitiationNetwork): Map<string, string> {
  const byHole = new Map<string, string[]>();
  for (const item of networkTies(network)) {
    const list = byHole.get(item.to_hole) ?? [];
    list.push(`${item.from_hole}@${item.delay_ms}`);
    byHole.set(item.to_hole, list);
  }
  return new Map(Array.from(byHole, ([hole, list]) => [hole, list.sort().join(",")]));
}

function starterSet(network: InitiationNetwork): string {
  const ids = network.starter_items?.length ? network.starter_items.map((item) => item.hole_id) : network.starters;
  return [...ids].sort().join(",");
}

/**
 * Что сменил пересчёт: число скважин, у которых другая входящая связь (откуда
 * или ступень; появилась или пропала), и другой ли набор стартовых (вруб).
 */
export function networkChangeSummary(prev: InitiationNetwork, next: InitiationNetwork): RetieSummary {
  const before = incoming(prev);
  const after = incoming(next);
  let changedTies = 0;
  for (const hole of new Set([...before.keys(), ...after.keys()])) {
    if (before.get(hole) !== after.get(hole)) changedTies += 1;
  }
  return { changedTies, cutChanged: starterSet(prev) !== starterSet(next) };
}

export function retieSummaryText(summary: RetieSummary): string {
  const parts: string[] = [];
  if (summary.changedTies) parts.push(`изменилось связей — ${summary.changedTies}`);
  if (summary.cutChanged) parts.push("вруб сменился");
  return `Коммутация пересчитана: ${parts.length ? parts.join(", ") : "связи прежние"}.`;
}
