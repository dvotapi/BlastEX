// Клиентские времена срабатывания сети (TASK-017, PR 4) — порт
// `design/timing.py::resolve_network` без событий по декам и боевикам.
//
// Правка связей на плане показывает времена и скважины «без сигнала» сразу,
// без запроса к серверу. Кратчайший путь от стартовых (`starter_items` со
// своей задержкой, иначе `starters` с нулём) по связям (`surface_connectors`,
// иначе `connectors`) и отрезкам шнура ДШ (расстояние в плане / скорость +
// реле, в обе стороны), плюс замедление в скважине. Электронные каналы и
// `electronic_times_ms` главнее связей. Сигнал проходит и через исключённую
// скважину — как на сервере; в ответ идут только включённые. Совпадение с
// сервером держит общая фикстура `testing/networkTimesFixture.json`.
import { networkTies, type Hole, type InitiationNetwork } from "../../types/design";

export type NetworkTimes = {
  /** Время срабатывания включённых скважин, получивших сигнал, мс. */
  times: Record<string, number>;
  /** Включённые скважины без сигнала, по номеру. */
  unsignaled: string[];
};

/** Скорость детонации ДШ, если у шнура её нет (`design/timing.py::DETCORD_VELOCITY_M_S`, каталог). */
const FALLBACK_VELOCITY_M_S = 7000;

type Edge = { to: string; delay: number };

function adjacency(network: InitiationNetwork, holes: Hole[], defaultVelocity: number): Map<string, Edge[]> {
  const edges = new Map<string, Edge[]>();
  const add = (from: string, to: string, delay: number) => {
    const list = edges.get(from);
    if (list) list.push({ to, delay });
    else edges.set(from, [{ to, delay }]);
  };
  for (const tie of networkTies(network)) add(tie.from_hole, tie.to_hole, Math.max(0, tie.delay_ms));
  const byId = new Map(holes.map((hole) => [hole.id, hole]));
  for (const cord of network.detonating_cords ?? []) {
    const velocity = cord.velocity_m_s > 0 ? cord.velocity_m_s : defaultVelocity;
    for (let i = 0; i + 1 < cord.hole_ids.length; i += 1) {
      const left = byId.get(cord.hole_ids[i]);
      const right = byId.get(cord.hole_ids[i + 1]);
      if (!left || !right) continue;
      const distance = Math.hypot(right.collar.x - left.collar.x, right.collar.y - left.collar.y);
      const delay = (distance / velocity) * 1000 + Math.max(0, cord.relay_delay_ms);
      add(left.id, right.id, delay);
      add(right.id, left.id, delay);
    }
  }
  return edges;
}

/** Двоичная куча по времени — для кратчайшего пути. */
class MinHeap {
  private items: [number, string][] = [];

  get size(): number {
    return this.items.length;
  }

  push(item: [number, string]): void {
    const items = this.items;
    items.push(item);
    let i = items.length - 1;
    while (i > 0) {
      const parent = (i - 1) >> 1;
      if (items[parent][0] <= items[i][0]) break;
      [items[parent], items[i]] = [items[i], items[parent]];
      i = parent;
    }
  }

  pop(): [number, string] {
    const items = this.items;
    const top = items[0];
    const last = items.pop()!;
    if (items.length) {
      items[0] = last;
      let i = 0;
      for (;;) {
        const left = 2 * i + 1;
        const right = left + 1;
        let smallest = i;
        if (left < items.length && items[left][0] < items[smallest][0]) smallest = left;
        if (right < items.length && items[right][0] < items[smallest][0]) smallest = right;
        if (smallest === i) break;
        [items[smallest], items[i]] = [items[i], items[smallest]];
        i = smallest;
      }
    }
    return top;
  }
}

function downholeFor(network: InitiationNetwork, holeId: string): number {
  const item = (network.downhole_connectors ?? []).find(
    (entry) => entry.hole_id === holeId && entry.deck_index == null && entry.primer_index == null,
  );
  if (item) return item.delay_ms;
  return network.downhole_delay_ms?.[holeId] ?? 0;
}

export function resolveNetworkTimes(
  network: InitiationNetwork,
  holes: Hole[],
  defaultVelocityMS: number = FALLBACK_VELOCITY_M_S,
): NetworkTimes {
  const enabled = new Set(holes.filter((hole) => hole.enabled).map((hole) => hole.id));
  const edges = adjacency(network, holes, defaultVelocityMS);

  const heap = new MinHeap();
  if (network.starter_items?.length) {
    for (const item of network.starter_items) if (enabled.has(item.hole_id)) heap.push([Math.max(0, item.delay_ms), item.hole_id]);
  } else {
    for (const id of network.starters ?? []) if (enabled.has(id)) heap.push([0, id]);
  }
  const surface = new Map<string, number>();
  while (heap.size) {
    const [t, id] = heap.pop();
    const known = surface.get(id);
    if (known !== undefined && known <= t) continue;
    surface.set(id, t);
    for (const edge of edges.get(id) ?? []) {
      const candidate = t + Math.max(0, edge.delay);
      const current = surface.get(edge.to);
      if (current === undefined || candidate < current) heap.push([candidate, edge.to]);
    }
  }

  const channels = new Map<string, number>();
  for (const item of network.electronic_channels ?? []) {
    if (enabled.has(item.hole_id) && item.deck_index == null && item.primer_index == null) channels.set(item.hole_id, item.time_ms);
  }
  const electronic = network.electronic_times_ms ?? {};
  const times: Record<string, number> = {};
  const unsignaled: string[] = [];
  for (const id of enabled) {
    const channel = channels.get(id);
    if (channel !== undefined) times[id] = channel;
    else if (Object.prototype.hasOwnProperty.call(electronic, id)) times[id] = electronic[id];
    else if (surface.has(id)) times[id] = surface.get(id)! + downholeFor(network, id);
    else unsignaled.push(id);
  }
  unsignaled.sort();
  return { times, unsignaled };
}
