import { describe, expect, it } from "vitest";
import { emptyNetwork, type InitiationNetwork } from "../../types/design";
import {
  isGeometryStale,
  isNetworkEmpty,
  markGeometryStale,
  markNetworkEdited,
  networkChangeSummary,
  networkOrigin,
  retieRequest,
  retieSummaryText,
} from "./retie";

function net(patch: Partial<InitiationNetwork>): InitiationNetwork {
  return { ...emptyNetwork(), ...patch };
}

function tie(from: string, to: string, delay = 42) {
  return { id: `sc-${from}-${to}`, from_hole: from, to_hole: to, delay_ms: delay, kind: "surface_nsi", product: "" };
}

const TRUNK = net({
  system: "detcord",
  starters: ["1-01"],
  surface_connectors: [tie("1-01", "1-02", 25), tie("1-01", "2-01")],
  timing_params: { scheme: "trunk_chains", origin: "template", trunk_ms: 25, chain_ms: 42, cut_flank: "left" },
});

describe("происхождение сети", () => {
  it("нет ключа origin — правленая", () => {
    expect(networkOrigin(net({ timing_params: { scheme: "row" } }))).toBe("edited");
    expect(networkOrigin(TRUNK)).toBe("template");
    expect(networkOrigin(net({ timing_params: { origin: "edited" } }))).toBe("edited");
  });

  it("ручная правка ставит edited, только если ключ уже есть", () => {
    expect(markNetworkEdited(TRUNK).timing_params.origin).toBe("edited");
    const old = net({ timing_params: { scheme: "row", interval_ms: 25 } });
    expect(markNetworkEdited(old)).toBe(old);
  });
});

describe("параметры пересчёта", () => {
  it("timing_params без служебных ключей и система сети", () => {
    const stale = markGeometryStale(TRUNK);
    expect(retieRequest(stale)).toEqual({
      scheme: "trunk_chains",
      params: { trunk_ms: 25, chain_ms: 42, cut_flank: "left", system: "detcord" },
    });
  });

  it("сеть до PR 3 и неизвестная схема — параметров не хватает", () => {
    expect(retieRequest(net({ timing_params: { scheme: "row", interval_ms: 25 } }))).toBeNull();
    expect(retieRequest(net({ timing_params: { scheme: "spiral", origin: "template" } }))).toBeNull();
  });
});

describe("пометка «устарела по геометрии»", () => {
  it("ставится и читается", () => {
    expect(isGeometryStale(TRUNK)).toBe(false);
    const stale = markGeometryStale(TRUNK);
    expect(isGeometryStale(stale)).toBe(true);
    expect(stale.timing_params.origin).toBe("template");
  });

  it("пустая сеть", () => {
    expect(isNetworkEmpty(emptyNetwork())).toBe(true);
    expect(isNetworkEmpty(TRUNK)).toBe(false);
    expect(isNetworkEmpty(net({ electronic_times_ms: { "1-01": 0 } }))).toBe(false);
  });
});

describe("сводка пересчёта", () => {
  it("смена входящей у одной скважины — одна связь, вруб тот же", () => {
    const next = { ...TRUNK, surface_connectors: [tie("1-01", "1-02", 25), tie("1-02", "2-01")] };
    expect(networkChangeSummary(TRUNK, next)).toEqual({ changedTies: 1, cutChanged: false });
  });

  it("смена ступени и появление связи считаются, другие стартовые — вруб сменился", () => {
    const next = {
      ...TRUNK,
      starters: ["1-03"],
      surface_connectors: [tie("1-01", "1-02", 42), tie("1-01", "2-01"), tie("1-03", "1-01", 25)],
    };
    expect(networkChangeSummary(TRUNK, next)).toEqual({ changedTies: 2, cutChanged: true });
  });

  it("текст", () => {
    expect(retieSummaryText({ changedTies: 3, cutChanged: true })).toBe("Коммутация пересчитана: изменилось связей — 3, вруб сменился.");
    expect(retieSummaryText({ changedTies: 0, cutChanged: false })).toBe("Коммутация пересчитана: связи прежние.");
    expect(retieSummaryText({ changedTies: 1, cutChanged: false })).toBe("Коммутация пересчитана: изменилось связей — 1.");
  });
});
