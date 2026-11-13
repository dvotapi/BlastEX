// Правки коммутации на плане (TASK-017, PR 4): чистые функции над сетью.
import { describe, expect, it } from "vitest";
import { networkTies, normalizeNetwork, type InitiationNetwork, type SurfaceConnector } from "../../types/design";
import {
  addTies,
  reconnectTie,
  removeTies,
  reverseTie,
  setDownholeDelay,
  setTiesDelay,
  stepCounts,
  tieEditNotice,
  toggleStarter,
} from "./tieEdits";

function tie(from: string, to: string, delay = 42): SurfaceConnector {
  return { id: `sc-${from}-${to}`, from_hole: from, to_hole: to, delay_ms: delay, kind: "surface_nsi", product: "" };
}

function net(ties: SurfaceConnector[], starters: string[] = ["a"], origin: string | null = "template"): InitiationNetwork {
  return normalizeNetwork({
    system: "nonel",
    surface_connectors: ties,
    connectors: ties.map(({ from_hole, to_hole, delay_ms, kind }) => ({ from_hole, to_hole, delay_ms, kind })),
    starter_items: starters.map((id) => ({ id: `st-${id}`, hole_id: id, delay_ms: 0, kind: "starter" })),
    starters,
    timing_params: origin ? { scheme: "trunk_chains", origin, trunk_ms: 25 } : {},
  });
}

const pairs = (network: InitiationNetwork) => networkTies(network).map((t) => `${t.from_hole}>${t.to_hole}@${t.delay_ms}`).sort();

describe("addTies — связь и протяжка", () => {
  it("протяжка через 4 скважины — 3 связи активной ступени, сеть правленая", () => {
    const result = addTies(net([]), ["a", "b", "c", "d"], 17);
    expect(pairs(result.network)).toEqual(["a>b@17", "b>c@17", "c>d@17"]);
    expect(result.network.timing_params.origin).toBe("edited");
    expect(result.changed).toBe(true);
    expect(result.network.connectors).toHaveLength(3);
    expect(result.network.surface_connectors.every((t) => t.kind === "surface_nsi")).toBe(true);
  });

  it("связь к скважине с входом заменяет прежнюю: у цели одна входящая", () => {
    const result = addTies(net([tie("a", "b"), tie("a", "c")]), ["b", "c"], 25);
    expect(pairs(result.network)).toEqual(["a>b@42", "b>c@25"]);
    expect(result.replaced.map((t) => t.id)).toEqual(["sc-a-c"]);
    expect(tieEditNotice(result)).toBe("Связь a → c заменена");
  });

  it("цикл не создаётся", () => {
    const base = net([tie("a", "b"), tie("b", "c")]);
    const result = addTies(base, ["c", "a"], 25);
    expect(result.changed).toBe(false);
    expect(result.network).toBe(base);
    expect(tieEditNotice(result)).toBe("Цикл: скважина a уже срабатывает раньше");
  });

  it("протяжка: отрезок с циклом пропускается, остальные ставятся", () => {
    const result = addTies(net([tie("a", "b"), tie("b", "c")]), ["b", "d", "a"], 25);
    expect(pairs(result.network)).toEqual(["a>b@42", "b>c@42", "b>d@25"]);
    expect(result.cycles).toEqual([{ from: "d", to: "a" }]);
    expect(tieEditNotice(result)).toBe("Цикл: скважина a уже срабатывает раньше");
  });

  it("исток без входа и не стартовая — становится стартовой", () => {
    const result = addTies(net([], []), ["x", "y"], 25);
    expect(result.network.starters).toEqual(["x"]);
    const kept = addTies(net([tie("a", "b")]), ["b", "c"], 25);
    expect(kept.network.starters).toEqual(["a"]);
  });

  it("сеть без origin (до PR 3) ключа не получает", () => {
    const result = addTies(net([], ["a"], null), ["a", "b"], 25);
    expect("origin" in result.network.timing_params).toBe(false);
  });

  it("та же связь с той же ступенью — без изменений", () => {
    const base = net([tie("a", "b", 25)]);
    expect(addTies(base, ["a", "b"], 25).network).toBe(base);
  });
});

describe("ступень, удаление, разворот, перецепка", () => {
  it("setTiesDelay меняет номинал выбранных", () => {
    const result = setTiesDelay(net([tie("a", "b"), tie("b", "c")]), ["sc-b-c"], 67);
    expect(pairs(result.network)).toEqual(["a>b@42", "b>c@67"]);
    expect(result.network.connectors.find((c) => c.to_hole === "c")?.delay_ms).toBe(67);
    expect(result.network.timing_params.origin).toBe("edited");
  });

  it("removeTies удаляет выбранные", () => {
    const result = removeTies(net([tie("a", "b"), tie("b", "c")]), ["sc-a-b"]);
    expect(pairs(result.network)).toEqual(["b>c@42"]);
    expect(result.network.connectors).toHaveLength(1);
  });

  it("разворот: связь в обратную сторону, вход у новой цели заменён", () => {
    const flipped = reverseTie(net([tie("a", "b"), tie("c", "d"), tie("a", "c")]), "sc-c-d");
    expect(pairs(flipped.network)).toEqual(["a>b@42", "d>c@42"]);
    expect(tieEditNotice(flipped)).toBe("Связь a → c заменена");
  });

  it("разворот, дающий цикл, отклоняется", () => {
    const base = net([tie("a", "b"), tie("b", "c"), tie("a", "c")]);
    const result = reverseTie(base, "sc-a-c");
    expect(result.changed).toBe(false);
    expect(result.network).toBe(base);
    expect(tieEditNotice(result)).toBe("Цикл: скважина a уже срабатывает раньше");
  });

  it("перецепка конца: новая цель, вход у неё заменён", () => {
    const result = reconnectTie(net([tie("a", "b"), tie("a", "c"), tie("c", "d")]), "sc-a-b", "to", "d");
    expect(pairs(result.network)).toEqual(["a>c@42", "a>d@42"]);
    expect(tieEditNotice(result)).toBe("Связь c → d заменена");
    const from = reconnectTie(net([tie("a", "b"), tie("a", "c")]), "sc-a-c", "from", "b");
    expect(pairs(from.network)).toEqual(["a>b@42", "b>c@42"]);
    expect(from.network.starters).toEqual(["a"]);
    // Начало на скважину без входа — она становится стартовой, как у новой связи.
    const fresh = reconnectTie(net([tie("a", "b")]), "sc-a-b", "from", "x");
    expect(pairs(fresh.network)).toEqual(["x>b@42"]);
    expect(fresh.network.starters).toEqual(["a", "x"]);
  });

  it("перецепка в цикл отклоняется — и началом, и концом", () => {
    const base = net([tie("a", "b"), tie("b", "c"), tie("c", "d")]);
    const byFrom = reconnectTie(base, "sc-b-c", "from", "d");
    expect(byFrom.changed).toBe(false);
    expect(byFrom.network).toBe(base);
    const byTo = reconnectTie(base, "sc-c-d", "to", "a");
    expect(byTo.changed).toBe(false);
    expect(tieEditNotice(byTo)).toBe("Цикл: скважина a уже срабатывает раньше");
  });
});

describe("стартовые и замедление в скважине", () => {
  it("стартер ставится и снимается", () => {
    const on = toggleStarter(net([]), "b");
    expect(on.network.starters).toEqual(["a", "b"]);
    expect(on.network.timing_params.origin).toBe("edited");
    expect(toggleStarter(on.network, "a").network.starters).toEqual(["b"]);
  });

  it("замедление в скважине — в карту, скважинный соединитель и детонатор", () => {
    const base = normalizeNetwork({
      ...net([]),
      downhole_delay_ms: { a: 500 },
      downhole_connectors: [{ id: "dh-a", hole_id: "a", delay_ms: 500, kind: "downhole_nsi", deck_index: null, primer_index: null, product: "" }],
      detonators: [{ id: "det-a", hole_id: "a", delay_ms: 500, product: "", kind: "nonel", deck_index: null, primer_index: null, channel_id: "" }],
    });
    const result = setDownholeDelay(base, ["a", "b"], 700);
    expect(result.network.downhole_delay_ms).toEqual({ a: 700, b: 700 });
    expect(result.network.downhole_connectors.map((d) => [d.hole_id, d.delay_ms])).toEqual([["a", 700], ["b", 700]]);
    expect(result.network.detonators[0].delay_ms).toBe(700);
    expect(setDownholeDelay(result.network, ["a"], 700).changed).toBe(false);
  });
});

describe("счётчики ступеней", () => {
  it("число связей каждой ступени", () => {
    expect(Object.fromEntries(stepCounts(net([tie("a", "b", 25), tie("b", "c", 42), tie("c", "d", 42)])))).toEqual({ 25: 1, 42: 2 });
  });
});
