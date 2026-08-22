// Единственный источник истины для документа паспорта БВР на клиенте:
// useReducer + стек undo/redo. Камера, выделение и режим инструмента — вне
// документа (не должны попадать в историю правок).
import type { BenchSurface, BlastDesign, ChargeRules, Hole, HoleLoad, InitiationNetwork, PatternParams } from "../../types/design";

export type DesignAction =
  | { type: "LOAD"; design: BlastDesign }
  | { type: "SET_NAME"; name: string }
  | { type: "SET_CONTOUR_VERTICES"; vertices: BlastDesign["contour"]["vertices"] }
  | { type: "TOGGLE_FREE_FACE"; edgeIndex: number }
  | { type: "SET_BENCH"; bench: Partial<BenchSurface> }
  | { type: "SET_PATTERN_PARAMS"; params: Partial<PatternParams> }
  | { type: "SET_HOLES"; holes: Hole[] }
  | { type: "MOVE_HOLES"; ids: string[]; dx: number; dy: number }
  | { type: "UPDATE_HOLE"; id: string; patch: Partial<Hole> }
  | { type: "ADD_HOLE"; hole: Hole }
  | { type: "DELETE_HOLES"; ids: string[] }
  | { type: "SET_CHARGE_RULES"; rules: Partial<ChargeRules> }
  | { type: "SET_LOADS"; loads: HoleLoad[] }
  | { type: "SET_NETWORK"; network: InitiationNetwork }
  | { type: "UNDO" }
  | { type: "REDO" };

export type DesignState = {
  past: BlastDesign[];
  present: BlastDesign;
  future: BlastDesign[];
};

const HISTORY_LIMIT = 50;

export function initDesignState(design: BlastDesign): DesignState {
  return { past: [], present: design, future: [] };
}

function edgeKey(index: number, total: number): number[] {
  return [index, (index + 1) % total];
}

function moveHole(hole: Hole, dx: number, dy: number): Hole {
  return {
    ...hole,
    collar: { ...hole.collar, x: hole.collar.x + dx, y: hole.collar.y + dy },
    toe: { ...hole.toe, x: hole.toe.x + dx, y: hole.toe.y + dy },
  };
}

function emptyNetwork(): InitiationNetwork {
  return { system: "nonel", starters: [], connectors: [], downhole_delay_ms: {}, electronic_times_ms: {} };
}

function pruneLoadsAndNetwork(document: BlastDesign, holeIds: Set<string>): Pick<BlastDesign, "loads" | "network"> {
  const loads = document.loads.filter((ld) => holeIds.has(ld.hole_id));
  const network = document.network;
  return {
    loads,
    network: {
      ...network,
      starters: network.starters.filter((id) => holeIds.has(id)),
      connectors: network.connectors.filter((c) => holeIds.has(c.from_hole) && holeIds.has(c.to_hole)),
      downhole_delay_ms: Object.fromEntries(Object.entries(network.downhole_delay_ms).filter(([id]) => holeIds.has(id))),
      electronic_times_ms: Object.fromEntries(Object.entries(network.electronic_times_ms).filter(([id]) => holeIds.has(id))),
    },
  };
}

function reduceDocument(document: BlastDesign, action: DesignAction): BlastDesign {
  switch (action.type) {
    case "LOAD":
      return action.design;
    case "SET_NAME":
      return { ...document, name: action.name };
    case "SET_CONTOUR_VERTICES": {
      const total = action.vertices.length;
      const free_faces = document.contour.free_faces.filter(([a, b]) => a >= 0 && a < total && b >= 0 && b < total);
      return {
        ...document,
        contour: { ...document.contour, vertices: action.vertices, free_faces },
      };
    }
    case "TOGGLE_FREE_FACE": {
      const total = document.contour.vertices.length;
      if (total < 2) return document;
      const edge = edgeKey(action.edgeIndex, total);
      const exists = document.contour.free_faces.some((f) => f[0] === edge[0] && f[1] === edge[1]);
      const free_faces = exists
        ? document.contour.free_faces.filter((f) => !(f[0] === edge[0] && f[1] === edge[1]))
        : [...document.contour.free_faces, edge];
      return { ...document, contour: { ...document.contour, free_faces } };
    }
    case "SET_BENCH":
      return { ...document, contour: { ...document.contour, bench: { ...document.contour.bench, ...action.bench } } };
    case "SET_PATTERN_PARAMS":
      return { ...document, pattern_params: { ...document.pattern_params, ...action.params } };
    case "SET_HOLES":
      return {
        ...document,
        holes: action.holes,
        loads: [],
        network: emptyNetwork(),
      };
    case "MOVE_HOLES": {
      const ids = new Set(action.ids);
      return {
        ...document,
        holes: document.holes.map((h) => (ids.has(h.id) ? moveHole(h, action.dx, action.dy) : h)),
      };
    }
    case "UPDATE_HOLE":
      return {
        ...document,
        holes: document.holes.map((h) => (h.id === action.id ? { ...h, ...action.patch } : h)),
      };
    case "ADD_HOLE":
      return { ...document, holes: [...document.holes, action.hole] };
    case "DELETE_HOLES": {
      const ids = new Set(action.ids);
      const holes = document.holes.filter((h) => !ids.has(h.id));
      const holeIds = new Set(holes.map((h) => h.id));
      return { ...document, holes, ...pruneLoadsAndNetwork(document, holeIds) };
    }
    case "SET_CHARGE_RULES":
      return { ...document, charge_rules: { ...document.charge_rules, ...action.rules } };
    case "SET_LOADS":
      return { ...document, loads: action.loads };
    case "SET_NETWORK":
      return { ...document, network: action.network };
    default:
      return document;
  }
}

const UNDOABLE: DesignAction["type"][] = [
  "SET_NAME",
  "SET_CONTOUR_VERTICES",
  "TOGGLE_FREE_FACE",
  "SET_BENCH",
  "SET_HOLES",
  "MOVE_HOLES",
  "UPDATE_HOLE",
  "ADD_HOLE",
  "DELETE_HOLES",
  "SET_LOADS",
  "SET_NETWORK",
];

export function designReducer(state: DesignState, action: DesignAction): DesignState {
  if (action.type === "UNDO") {
    if (state.past.length === 0) return state;
    const previous = state.past[state.past.length - 1];
    return {
      past: state.past.slice(0, -1),
      present: previous,
      future: [state.present, ...state.future].slice(0, HISTORY_LIMIT),
    };
  }
  if (action.type === "REDO") {
    if (state.future.length === 0) return state;
    const [next, ...rest] = state.future;
    return { past: [...state.past, state.present].slice(-HISTORY_LIMIT), present: next, future: rest };
  }

  const nextPresent = reduceDocument(state.present, action);
  if (nextPresent === state.present) return state;

  if (
    action.type === "SET_PATTERN_PARAMS" ||
    action.type === "SET_CHARGE_RULES" ||
    !UNDOABLE.includes(action.type)
  ) {
    // Параметры раскладки не создают отдельный шаг истории — они меняются
    // на каждое нажатие клавиши в форме, а не как правка документа.
    return { ...state, present: nextPresent };
  }

  return {
    past: [...state.past, state.present].slice(-HISTORY_LIMIT),
    present: nextPresent,
    future: [],
  };
}
