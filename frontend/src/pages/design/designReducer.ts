// Единственный источник истины для документа паспорта БВР на клиенте:
// useReducer + стек undo/redo. Камера, выделение и режим инструмента — вне
// документа (не должны попадать в историю правок).
import { collarZFromSurfaces } from "../../lib/surfaces";
import type {
  BenchSurface,
  BlastDesign,
  ChargeRules,
  CoordinateSystem,
  Hole,
  HoleLoad,
  InitiationNetwork,
  PatternParams,
  SurfaceKind,
  SurfaceModel,
  BlastDomain,
} from "../../types/design";
import { emptyCoordinateSystem, emptyHoleGeology, emptySurfaces } from "../../types/design";

export type DesignAction =
  | { type: "LOAD"; design: BlastDesign }
  | { type: "SET_NAME"; name: string }
  | { type: "SET_CONTOUR_VERTICES"; vertices: BlastDesign["contour"]["vertices"]; free_faces?: number[][]; coalesce?: boolean }
  | { type: "TOGGLE_FREE_FACE"; edgeIndex: number }
  | { type: "SET_BENCH"; bench: Partial<BenchSurface> }
  | { type: "SET_COORDINATE_SYSTEM"; patch: Partial<CoordinateSystem> }
  | { type: "SET_SURFACE"; surface: SurfaceModel }
  | { type: "CLEAR_SURFACE"; kind: SurfaceKind }
  | { type: "SET_PATTERN_PARAMS"; params: Partial<PatternParams> }
  | { type: "SET_HOLES"; holes: Hole[] }
  | { type: "MOVE_HOLES"; ids: string[]; dx: number; dy: number }
  | { type: "UPDATE_HOLE"; id: string; patch: Partial<Hole> }
  | { type: "ADD_HOLE"; hole: Hole }
  | { type: "DELETE_HOLES"; ids: string[] }
  | { type: "SET_HOLES_ENABLED"; ids: string[]; enabled: boolean }
  | { type: "SET_CHARGE_RULES"; rules: Partial<ChargeRules> }
  | { type: "SET_LOADS"; loads: HoleLoad[] }
  | { type: "SET_NETWORK"; network: InitiationNetwork }
  | { type: "SET_DOMAINS"; domains: BlastDomain[] }
  | { type: "UPSERT_DOMAIN"; domain: BlastDomain }
  | { type: "DELETE_DOMAIN"; id: string }
  | { type: "SET_WATER_TABLE"; water_table_z_m: number | null }
  | { type: "SET_HOLE_GEOLOGY"; holes: Hole[] }
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

function moveHole(hole: Hole, dx: number, dy: number, document: BlastDesign): Hole {
  const x = hole.collar.x + dx;
  const y = hole.collar.y + dy;
  const z = collarZFromSurfaces(document.surfaces, x, y, hole.collar.z);
  return {
    ...hole,
    collar: { ...hole.collar, x, y, z },
    toe: { ...hole.toe, x: hole.toe.x + dx, y: hole.toe.y + dy, z: hole.toe.z + (z - hole.collar.z) },
  };
}

function normalizeHole(hole: Hole): Hole {
  return { ...emptyHoleGeology(), ...hole };
}

function normalizeDesign(design: BlastDesign): BlastDesign {
  return {
    ...design,
    coordinate_system: { ...emptyCoordinateSystem(), ...design.coordinate_system },
    surfaces: { ...emptySurfaces(), ...design.surfaces },
    domains: (design.domains ?? []).map((domain) => ({
      ...domain,
      spacing_a_m: domain.spacing_a_m ?? null,
      burden_b_m: domain.burden_b_m ?? null,
    })),
    water_table_z_m: design.water_table_z_m ?? null,
    holes: (design.holes ?? []).map(normalizeHole),
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
      return normalizeDesign(action.design);
    case "SET_NAME":
      return { ...document, name: action.name };
    case "SET_CONTOUR_VERTICES": {
      // Вставка и удаление вершин присылают пересчитанные пометки откосов:
      // индексы рёбер при этом сдвигаются, и сохранить старые нельзя.
      const total = action.vertices.length;
      const source = action.free_faces ?? document.contour.free_faces;
      const free_faces = source.filter(([a, b]) => a >= 0 && a < total && b >= 0 && b < total);
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
    case "SET_COORDINATE_SYSTEM":
      return { ...document, coordinate_system: { ...document.coordinate_system, ...action.patch } };
    case "SET_SURFACE":
      return { ...document, surfaces: { ...document.surfaces, [action.surface.kind]: action.surface } };
    case "CLEAR_SURFACE":
      return { ...document, surfaces: { ...document.surfaces, [action.kind]: null } };
    case "SET_PATTERN_PARAMS":
      return { ...document, pattern_params: { ...document.pattern_params, ...action.params } };
    case "SET_HOLES":
      return {
        ...document,
        holes: action.holes.map(normalizeHole),
        loads: [],
        network: emptyNetwork(),
      };
    case "MOVE_HOLES": {
      const ids = new Set(action.ids);
      return {
        ...document,
        holes: document.holes.map((h) => {
          if (!ids.has(h.id)) return h;
          const moved = moveHole(h, action.dx, action.dy, document);
          return { ...moved, intervals: [], water_intervals: [] };
        }),
      };
    }
    case "UPDATE_HOLE":
      return {
        ...document,
        holes: document.holes.map((h) => {
          if (h.id !== action.id) return h;
          const next = { ...h, ...action.patch };
          if (action.patch.collar || action.patch.toe) {
            next.intervals = [];
            next.water_intervals = [];
          }
          return next;
        }),
      };
    case "ADD_HOLE":
      return { ...document, holes: [...document.holes, normalizeHole(action.hole)] };
    case "SET_HOLES_ENABLED": {
      // Отключённая скважина остаётся в паспорте и на плане, но выпадает из
      // объёмов, погонажа, заряжания и тайминга — их считает сервер по флагу.
      const ids = new Set(action.ids);
      if (!ids.size) return document;
      return {
        ...document,
        holes: document.holes.map((h) => (ids.has(h.id) ? { ...h, enabled: action.enabled } : h)),
      };
    }
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
    case "SET_DOMAINS":
      return { ...document, domains: action.domains };
    case "UPSERT_DOMAIN": {
      const exists = document.domains.some((d) => d.id === action.domain.id);
      return {
        ...document,
        domains: exists
          ? document.domains.map((d) => (d.id === action.domain.id ? action.domain : d))
          : [...document.domains, action.domain],
      };
    }
    case "DELETE_DOMAIN":
      return { ...document, domains: document.domains.filter((d) => d.id !== action.id) };
    case "SET_WATER_TABLE":
      return { ...document, water_table_z_m: action.water_table_z_m };
    case "SET_HOLE_GEOLOGY": {
      const byId = new Map(action.holes.map((h) => [h.id, h]));
      return {
        ...document,
        holes: document.holes.map((h) => {
          const next = byId.get(h.id);
          if (!next) return h;
          return {
            ...h,
            intervals: next.intervals ?? [],
            water_intervals: next.water_intervals ?? [],
            measured_intervals: next.measured_intervals ?? h.measured_intervals,
            measured_water_intervals: next.measured_water_intervals ?? h.measured_water_intervals,
          };
        }),
      };
    }
    default:
      return document;
  }
}

const UNDOABLE: DesignAction["type"][] = [
  "SET_NAME",
  "SET_CONTOUR_VERTICES",
  "TOGGLE_FREE_FACE",
  "SET_BENCH",
  "SET_SURFACE",
  "CLEAR_SURFACE",
  "SET_HOLES",
  "MOVE_HOLES",
  "UPDATE_HOLE",
  "ADD_HOLE",
  "DELETE_HOLES",
  "SET_HOLES_ENABLED",
  "SET_LOADS",
  "SET_NETWORK",
  "SET_DOMAINS",
  "UPSERT_DOMAIN",
  "DELETE_DOMAIN",
  "SET_WATER_TABLE",
  "SET_HOLE_GEOLOGY",
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
    (action.type === "SET_CONTOUR_VERTICES" && action.coalesce) ||
    !UNDOABLE.includes(action.type)
  ) {
    // Параметры раскладки не создают отдельный шаг истории — они меняются
    // на каждое нажатие клавиши в форме, а не как правка документа.
    // Так же и продолжение перетаскивания вершины (coalesce): шаг истории
    // создаёт только первое смещение, дальше правится уже текущее состояние.
    return { ...state, present: nextPresent };
  }

  return {
    past: [...state.past, state.present].slice(-HISTORY_LIMIT),
    present: nextPresent,
    future: [],
  };
}
