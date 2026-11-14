// Единственный источник истины для документа паспорта БВР на клиенте:
// useReducer + стек undo/redo. Камера, выделение и режим инструмента — вне
// документа (не должны попадать в историю правок).
import { faceAngleForImportedBlock } from "../../lib/faceAngle";
import { renameHoleIds } from "./holeRenumber";
import { clearMoved, isMovedHole, layoutAxes, markMoved, type LayoutAxes } from "./holeMove";
import { isGeometryStale, isNetworkEmpty, markGeometryStale, networkOrigin, retieRequest } from "./retie";
import { isRecordFrozen } from "../../lib/lifecycle";
import { collarZFromSurfaces } from "../../lib/surfaces";
import type { CadCrs } from "../../types/cad";
import type {
  BenchSurface,
  BlastDesign,
  CadContourInfo,
  ChargeRules,
  CoordinateSystem,
  Hole,
  HoleLoad,
  DetonatingCord,
  InitiationNetwork,
  PatternParams,
  SurfaceKind,
  SurfaceModel,
  BlastDomain,
  Receptor,
  VibrationMeasurement,
  VibrationModel,
  AsDrilledHole,
  AsChargedHole,
  AsFiredHole,
  BlastResult,
  SurveyApplication,
} from "../../types/design";
import {
  defaultVibrationModel,
  emptyCoordinateSystem,
  emptyHoleGeology,
  emptyNetwork,
  emptySurfaces,
  normalizeNetwork,
} from "../../types/design";

export type DesignAction =
  /**
   * Открыт другой документ (паспорт, новый, ревизия, тот же после смены
   * статуса): история с нуля. `base` — `saved` на момент запроса: если с тех
   * пор открыт другой паспорт, ответ устарел и не применяется.
   */
  | { type: "LOAD"; design: BlastDesign; base?: BlastDesign }
  /**
   * Новые номера скважин по правилу эшелонов: id и все ссылки на них, один шаг
   * отмены. `holes` — скважины, по которым сервер считал соответствие: другие
   * (открыли другой проект, правили скважины) — ответ устарел и не применяется.
   */
  | { type: "RENUMBER_HOLES"; mapping: Record<string, string>; holes: Hole[] }
  /** Ответ сервера на сохранение открытого паспорта: история правок остаётся. */
  | { type: "SAVED"; design: BlastDesign; base?: BlastDesign }
  | { type: "SET_NAME"; name: string }
  /** Порода блока: по ней анализ берёт границы темпа отбойки из справочника. */
  | { type: "SET_ROCK_NAME"; rock_name: string }
  | { type: "SET_CONTOUR_VERTICES"; vertices: BlastDesign["contour"]["vertices"]; free_faces?: number[][]; coalesce?: boolean }
  | { type: "TOGGLE_FREE_FACE"; edgeIndex: number }
  | {
      type: "APPLY_CAD_CONTOUR";
      vertices: BlastDesign["contour"]["vertices"];
      free_faces: number[][];
      bench: Partial<BenchSurface>;
      cad: CadContourInfo;
      /** Кровля из чертежа (TASK-013, PR 3): ставится в `surfaces.top`, подошва — числом. */
      surface: SurfaceModel;
      /** СК объекта (PR 4): ставится в паспорт подтверждённой; null — СК паспорта не меняется. */
      crs?: CadCrs | null;
    }
  | { type: "SET_BENCH"; bench: Partial<BenchSurface> }
  /** Источник линии подошвы блока: "survey" — съёмка, null — по углу (ключ убирается). */
  | { type: "SET_TOE_SOURCE"; toe_source: "survey" | null }
  | { type: "SET_COORDINATE_SYSTEM"; patch: Partial<CoordinateSystem> }
  | { type: "SET_SURFACE"; surface: SurfaceModel }
  | { type: "CLEAR_SURFACE"; kind: SurfaceKind }
  | { type: "SET_PATTERN_PARAMS"; params: Partial<PatternParams> }
  | { type: "SET_HOLES"; holes: Hole[] }
  /**
   * Вариант подбора раскладки (часть 4в): скважины, сеть «Магистраль +
   * цепочки» и параметры сетки варианта — одной правкой, один шаг отмены.
   * Параметры заменяются целиком: ключи прежней схемы первого ряда уходят.
   */
  | {
      type: "APPLY_LAYOUT";
      holes: Hole[];
      network: InitiationNetwork;
      pattern_params: Record<string, unknown>;
    }
  /**
   * «Применить съёмку» (TASK-014, PR 5а): ответ `POST /design/survey/apply`
   * целиком, один шаг отмены. `loads: null` — заряды прежние.
   */
  | {
      type: "APPLY_SURVEY";
      holes: Hole[];
      loads: HoleLoad[] | null;
      as_drilled_holes: AsDrilledHole[];
      survey_application: SurveyApplication;
      changed_ids: string[];
    }
  /** Ответ пересчёта по кровле и подошве: новые устья и забои, вне истории отмены. */
  | { type: "RECOMPUTE_HOLES"; holes: Hole[] }
  // `series` — время нажатия стрелки, мс: нажатия подряд склеиваются в одну
  // запись отмены (`MOVE_SERIES_GAP_MS`); сдвиг мышью идёт без него.
  // `axes` — оси раскладки, в которых копится смещение от узла (TASK-017,
  // PR 2): страница берёт их у формы «Сетка»; без них — по параметрам паспорта.
  | { type: "MOVE_HOLES"; ids: string[]; dx: number; dy: number; series?: number; axes?: LayoutAxes }
  /** «Вернуть в узел сетки»: устье — в узел, пометка сдвига снимается (TASK-017, PR 2). */
  | { type: "RETURN_TO_NODE"; ids: string[] }
  /**
   * Сеть, пересчитанная после сдвига (TASK-017, PR 3). `base` — документ, по
   * которому спрошен пересчёт: документ с тех пор сменился — ответ не
   * применяется. `merge` — автопересчёт: вливается в запись отмены сдвига
   * (одна отмена возвращает и скважины, и прежнюю сеть); иначе — своя запись.
   */
  | { type: "RETIE_NETWORK"; network: InitiationNetwork; base: BlastDesign; merge: boolean }
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
  | { type: "SET_RECEPTORS"; receptors: Receptor[] }
  | { type: "UPSERT_RECEPTOR"; receptor: Receptor }
  | { type: "DELETE_RECEPTOR"; id: string }
  | { type: "SET_VIBRATION_MODELS"; models: VibrationModel[] }
  | { type: "UPSERT_VIBRATION_MODEL"; model: VibrationModel }
  | { type: "SET_VIBRATION_MEASUREMENTS"; measurements: VibrationMeasurement[] }
  | { type: "UPSERT_MEASUREMENT"; measurement: VibrationMeasurement }
  | { type: "DELETE_MEASUREMENT"; id: string }
  | { type: "SET_AS_DRILLED"; holes: AsDrilledHole[] }
  | { type: "UPSERT_AS_DRILLED"; hole: AsDrilledHole }
  | { type: "DELETE_AS_DRILLED"; designHoleId: string }
  | { type: "SET_AS_CHARGED"; holes: AsChargedHole[] }
  | { type: "UPSERT_AS_CHARGED"; hole: AsChargedHole }
  | { type: "DELETE_AS_CHARGED"; designHoleId: string }
  | { type: "SET_AS_FIRED"; holes: AsFiredHole[] }
  | { type: "UPSERT_AS_FIRED"; hole: AsFiredHole }
  | { type: "DELETE_AS_FIRED"; designHoleId: string }
  | { type: "SET_BLAST_RESULT"; result: BlastResult | null }
  | { type: "UNDO" }
  | { type: "REDO" };

export type DesignState = {
  past: BlastDesign[];
  present: BlastDesign;
  future: BlastDesign[];
  /** Паспорт, как он лежит на сервере: последняя загрузка или ответ сохранения. */
  saved: BlastDesign;
  /**
   * Последнее нажатие серии стрелок (TASK-017): когда, какой документ оно
   * дало и какие скважины двигало. Серия продолжается, только пока документ
   * тот же — любое другое действие, отмена или загрузка меняют `present`, и
   * серия рвётся сама, — и двигаются те же скважины (смена выделения документ
   * не меняет, но начинает новую серию).
   */
  moveSeries?: { at: number; present: BlastDesign; ids: string };
  /**
   * Документ, который дал сдвиг скважин при сети шаблона (TASK-017, PR 3):
   * пока он на экране, страница пересчитывает коммутацию сама. `series` —
   * сдвиг стрелками: пересчёт ждёт конца серии. Открытие паспорта с уже
   * помеченной сетью отметки не даёт — пересчёт только от сдвига.
   */
  autoRetie?: { present: BlastDesign; series: boolean };
};

/** Пауза между нажатиями стрелок, после которой сдвиг — новая запись отмены, мс. */
export const MOVE_SERIES_GAP_MS = 1000;

const HISTORY_LIMIT = 50;

/**
 * Отмена и повтор закрыты только у закрытого паспорта. История начинается
 * заново при каждой смене статуса, поэтому в ней лишь правки, которые статус
 * разрешает (на проверке — название, утверждённому — исполнение и замер), и
 * отмена не возвращает ни прежний статус, ни проектную часть.
 */
export function historyLocked(status: string | undefined | null): boolean {
  return isRecordFrozen(status);
}

export function initDesignState(design: BlastDesign): DesignState {
  return { past: [], present: design, future: [], saved: design };
}

/** Поля, которые ведёт сервер: принадлежность паспорта и его статус, а не правки. */
type ServerFields = Pick<
  BlastDesign,
  "design_id" | "version" | "updated_at" | "lifecycle_status" | "revision" | "parent_design_id" | "designed_sha256" | "lifecycle_events"
>;

function serverFields(design: BlastDesign): ServerFields {
  return {
    design_id: design.design_id,
    version: design.version,
    updated_at: design.updated_at,
    lifecycle_status: design.lifecycle_status,
    revision: design.revision,
    parent_design_id: design.parent_design_id,
    designed_sha256: design.designed_sha256,
    lifecycle_events: design.lifecycle_events,
  };
}

function edgeKey(index: number, total: number): number[] {
  return [index, (index + 1) % total];
}

/**
 * Сеть после смены скважин (сдвиг, добавление, удаление, исключение, вид):
 * непустая помечается «устаревшей по геометрии» (TASK-017, PR 3 и PR 5).
 * Непустая — всегда новый объект: по нему `designReducer` видит, что действие
 * сменило скважины (и при уже стоящей пометке ставит пересчёт снова).
 */
function staleNetwork(source: InitiationNetwork): InitiationNetwork {
  const network = normalizeNetwork(source);
  return isNetworkEmpty(network) ? source : markGeometryStale(network);
}

function moveHole(hole: Hole, dx: number, dy: number, document: BlastDesign): Hole {
  const x = hole.collar.x + dx;
  const y = hole.collar.y + dy;
  // Отметку устья, заданную руками, сдвиг в плане не трогает (TASK-013, PR 3).
  const z = hole.manual?.includes("collar_z") ? hole.collar.z : collarZFromSurfaces(document.surfaces, x, y, hole.collar.z);
  return {
    ...hole,
    collar: { ...hole.collar, x, y, z },
    toe: { ...hole.toe, x: hole.toe.x + dx, y: hole.toe.y + dy, z: hole.toe.z + (z - hole.collar.z) },
  };
}

function samePoint(a: Hole["collar"], b: Hole["collar"]): boolean {
  return a.x === b.x && a.y === b.y && a.z === b.z;
}

/** Ось скважины та же: геологию, посчитанную по `b`, можно ставить скважине `a`. */
export function sameAxis(a: Hole, b: Hole): boolean {
  return samePoint(a.collar, b.collar) && samePoint(a.toe, b.toe);
}

/** Сколько скважин ответа геологии уже с другой осью в документе. */
export function changedAxes(holes: Hole[], response: Hole[]): number {
  const byId = new Map(holes.map((hole) => [hole.id, hole]));
  return response.filter((item) => {
    const hole = byId.get(item.id);
    return hole !== undefined && !sameAxis(hole, item);
  }).length;
}

function normalizeHole(hole: Hole): Hole {
  return { ...emptyHoleGeology(), ...hole };
}

function normalizeDesign(design: BlastDesign): BlastDesign {
  return {
    ...design,
    contour: { ...design.contour, cad: design.contour.cad ?? null },
    coordinate_system: { ...emptyCoordinateSystem(), ...design.coordinate_system },
    surfaces: { ...emptySurfaces(), ...design.surfaces },
    domains: (design.domains ?? []).map((domain) => ({
      ...domain,
      spacing_a_m: domain.spacing_a_m ?? null,
      burden_b_m: domain.burden_b_m ?? null,
    })),
    water_table_z_m: design.water_table_z_m ?? null,
    holes: (design.holes ?? []).map(normalizeHole),
    network: normalizeNetwork(design.network),
    receptors: design.receptors ?? [],
    vibration_models: design.vibration_models?.length ? design.vibration_models : [defaultVibrationModel()],
    vibration_measurements: design.vibration_measurements ?? [],
    as_drilled_holes: design.as_drilled_holes ?? [],
    as_charged_holes: design.as_charged_holes ?? [],
    as_fired_holes: design.as_fired_holes ?? [],
    blast_result: design.blast_result ?? null,
    lifecycle_status: design.lifecycle_status || "draft",
    revision: design.revision ?? 0,
    parent_design_id: design.parent_design_id ?? "",
    designed_sha256: design.designed_sha256 ?? "",
    lifecycle_events: design.lifecycle_events ?? [],
  };
}

/**
 * Шнур без удалённых скважин: рвётся на каждой, а не склеивается через неё
 * (прямой отрезок мимо удалённой дал бы фантомное время; сервер отрезок с
 * отсутствующей скважиной тоже пропускает). Куски короче двух скважин уходят.
 */
function cordRuns(cord: DetonatingCord, holeIds: Set<string>): DetonatingCord[] {
  const runs: string[][] = [];
  let run: string[] = [];
  for (const id of [...cord.hole_ids, null]) {
    if (id !== null && holeIds.has(id)) {
      run.push(id);
      continue;
    }
    if (run.length >= 2) runs.push(run);
    run = [];
  }
  if (runs.length === 1 && runs[0].length === cord.hole_ids.length) return [cord];
  return runs.map((hole_ids, index) => ({ ...cord, id: index ? `${cord.id}-${index + 1}` : cord.id, hole_ids }));
}

function pruneLoadsAndNetwork(document: BlastDesign, holeIds: Set<string>): Pick<BlastDesign, "loads" | "network"> {
  const loads = document.loads.filter((ld) => holeIds.has(ld.hole_id));
  const network = normalizeNetwork(document.network);
  return {
    loads,
    network: {
      ...network,
      starters: network.starters.filter((id) => holeIds.has(id)),
      connectors: network.connectors.filter((c) => holeIds.has(c.from_hole) && holeIds.has(c.to_hole)),
      downhole_delay_ms: Object.fromEntries(Object.entries(network.downhole_delay_ms).filter(([id]) => holeIds.has(id))),
      electronic_times_ms: Object.fromEntries(Object.entries(network.electronic_times_ms).filter(([id]) => holeIds.has(id))),
      detonators: network.detonators.filter((item) => holeIds.has(item.hole_id)),
      surface_connectors: network.surface_connectors.filter((item) => holeIds.has(item.from_hole) && holeIds.has(item.to_hole)),
      downhole_connectors: network.downhole_connectors.filter((item) => holeIds.has(item.hole_id)),
      detonating_cords: network.detonating_cords.flatMap((cord) => cordRuns(cord, holeIds)),
      starter_items: network.starter_items.filter((item) => holeIds.has(item.hole_id)),
      electronic_channels: network.electronic_channels.filter((item) => holeIds.has(item.hole_id)),
      firing_events: network.firing_events.filter((item) => holeIds.has(item.hole_id)),
      selected_hole_ids: network.selected_hole_ids.filter((id) => holeIds.has(id)),
    },
  };
}

function reduceDocument(document: BlastDesign, action: DesignAction): BlastDesign {
  switch (action.type) {
    case "SET_NAME":
      return { ...document, name: action.name };
    case "SET_ROCK_NAME":
      return { ...document, rock_name: action.rock_name };
    case "SET_CONTOUR_VERTICES": {
      // Вставка и удаление вершин присылают пересчитанные пометки откосов:
      // индексы рёбер при этом сдвигаются, и сохранить старые нельзя.
      const total = action.vertices.length;
      const source = action.free_faces ?? document.contour.free_faces;
      const free_faces = source.filter(([a, b]) => a >= 0 && a < total && b >= 0 && b < total);
      // Контур из чертежа, сдвинутый в плане, уже не совпадает с чертежом.
      // Смена одних отметок (драпировка по поверхности) — не правка контура.
      const cad = document.contour.cad;
      const movedInPlan =
        action.vertices.length !== document.contour.vertices.length ||
        action.vertices.some((vertex, index) => {
          const before = document.contour.vertices[index];
          return vertex.x !== before.x || vertex.y !== before.y;
        });
      return {
        ...document,
        contour: {
          ...document.contour,
          vertices: action.vertices,
          free_faces,
          ...(cad && movedInPlan && !cad.edited ? { cad: { ...cad, edited: true } } : {}),
        },
      };
    }
    case "APPLY_CAD_CONTOUR": {
      // Построение блока из чертежа — одна правка: контур, откосы, отметки
      // уступа, данные чертежа и кровля; поверхность подошвы снимается
      // (подошва — проектная отметка числом); скважины, заряды и сеть прежнего
      // контура очищаются.
      const cleared = reduceDocument(document, { type: "SET_HOLES", holes: [] });
      // СК объекта — и паспорту, и кровле из того же чертежа (кровля
      // строится в «local»); без СК объекта обе остаются как были.
      const withCrs = (system: CoordinateSystem): CoordinateSystem =>
        action.crs
          ? { ...system, name: action.crs.name, epsg: action.crs.epsg, height_system: action.crs.height_system, confirmed: true }
          : system;
      return {
        ...cleared,
        contour: {
          ...cleared.contour,
          vertices: action.vertices,
          free_faces: action.free_faces,
          bench: {
            ...cleared.contour.bench,
            ...action.bench,
            face_angle_deg: faceAngleForImportedBlock(action.bench.face_angle_deg ?? cleared.contour.bench.face_angle_deg),
          },
          cad: action.cad,
        },
        surfaces: {
          ...cleared.surfaces,
          top: { ...action.surface, coordinate_system: withCrs(action.surface.coordinate_system) },
          floor: null,
        },
        coordinate_system: withCrs(cleared.coordinate_system),
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
    case "SET_TOE_SOURCE": {
      // Ключ — только у выбранной съёмки: «по углу» — умолчание, паспорт без ключа.
      const { toe_source: _previous, ...contour } = document.contour;
      return {
        ...document,
        contour: action.toe_source === "survey" ? { ...contour, toe_source: "survey" } : contour,
      };
    }
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
        as_drilled_holes: [],
        as_charged_holes: [],
        as_fired_holes: [],
        blast_result: null,
      };
    case "RENUMBER_HOLES":
      return action.holes === document.holes ? renameHoleIds(document, action.mapping) : document;
    case "APPLY_LAYOUT": {
      // Как новая сетка: заряды и исполнение прежней раскладки сбрасываются.
      const cleared = reduceDocument(document, { type: "SET_HOLES", holes: action.holes });
      // Параметры — из действия: по их значению страница узнаёт, что форму
      // «Сетка» надо взять из документа (применение, отмена, повтор).
      return { ...cleared, network: normalizeNetwork(action.network), pattern_params: action.pattern_params };
    }
    case "APPLY_SURVEY": {
      // Коммутация устаревает, только если у изменённой скважины сменились устье
      // или забой; одна вода сети не касается.
      const previous = new Map(document.holes.map((h) => [h.id, h]));
      const changed = new Set(action.changed_ids);
      const geometryChanged = action.holes.some((h) => {
        if (!changed.has(h.id)) return false;
        const old = previous.get(h.id);
        return !old || !samePoint(old.collar, h.collar) || !samePoint(old.toe, h.toe);
      });
      return {
        ...document,
        holes: action.holes.map(normalizeHole),
        loads: action.loads ?? document.loads,
        as_drilled_holes: action.as_drilled_holes,
        survey_applications: [...(document.survey_applications ?? []), action.survey_application],
        network: geometryChanged ? staleNetwork(document.network) : document.network,
      };
    }
    case "RECOMPUTE_HOLES": {
      // Только геометрия: устье и забой. Прочие поля скважины (диаметр, вид,
      // ручные флаги) — как в документе; геология старой оси сбрасывается.
      const byId = new Map(action.holes.map((item) => [item.id, item]));
      let changed = false;
      const holes = document.holes.map((h) => {
        const next = byId.get(h.id);
        if (!next || (samePoint(h.collar, next.collar) && samePoint(h.toe, next.toe))) return h;
        changed = true;
        return { ...h, collar: next.collar, toe: next.toe, intervals: [], water_intervals: [] };
      });
      return changed ? { ...document, holes } : document;
    }
    case "MOVE_HOLES": {
      const ids = new Set(action.ids);
      const azimuth = Number(document.pattern_params?.row_azimuth_deg ?? 0);
      const axes = action.axes ?? layoutAxes(azimuth, document.contour);
      return {
        ...document,
        holes: document.holes.map((h) => {
          if (!ids.has(h.id)) return h;
          const moved = moveHole(h, action.dx, action.dy, document);
          return markMoved({ ...moved, intervals: [], water_intervals: [] }, h, axes);
        }),
        network: staleNetwork(document.network),
      };
    }
    case "RETURN_TO_NODE": {
      const ids = new Set(action.ids);
      let changed = false;
      const holes = document.holes.map((h) => {
        if (!ids.has(h.id) || !isMovedHole(h) || !h.manual_offset) return h;
        changed = true;
        const { node_x, node_y } = h.manual_offset;
        const back = moveHole(h, node_x - h.collar.x, node_y - h.collar.y, document);
        return clearMoved({ ...back, collar: { ...back.collar, x: node_x, y: node_y }, intervals: [], water_intervals: [] });
      });
      return changed ? { ...document, holes, network: staleNetwork(document.network) } : document;
    }
    case "UPDATE_HOLE": {
      // Вид скважины решает, войдёт ли она в сеть шаблона (контурная, стенка,
      // вид основной сетки): смена вида делает коммутацию устаревшей (PR 5).
      let kindChanged = false;
      const holes = document.holes.map((h) => {
        if (h.id !== action.id) return h;
        const next = { ...h, ...action.patch };
        if (action.patch.collar || action.patch.toe) {
          next.intervals = [];
          next.water_intervals = [];
        }
        if (next.kind !== h.kind) kindChanged = true;
        return next;
      });
      return { ...document, holes, ...(kindChanged ? { network: staleNetwork(document.network) } : {}) };
    }
    case "ADD_HOLE":
      return {
        ...document,
        holes: [...document.holes, normalizeHole(action.hole)],
        network: staleNetwork(document.network),
      };
    case "SET_HOLES_ENABLED": {
      // Отключённая скважина остаётся в паспорте и на плане, но выпадает из
      // объёмов, погонажа, заряжания и тайминга — их считает сервер по флагу.
      const ids = new Set(action.ids);
      if (!ids.size) return document;
      let changed = false;
      const holes = document.holes.map((h) => {
        if (!ids.has(h.id)) return h;
        if (h.enabled !== action.enabled) changed = true;
        return { ...h, enabled: action.enabled };
      });
      return { ...document, holes, ...(changed ? { network: staleNetwork(document.network) } : {}) };
    }
    case "DELETE_HOLES": {
      const ids = new Set(action.ids);
      const holes = document.holes.filter((h) => !ids.has(h.id));
      const holeIds = new Set(holes.map((h) => h.id));
      const pruned = pruneLoadsAndNetwork(document, holeIds);
      return {
        ...document,
        holes,
        as_drilled_holes: document.as_drilled_holes.filter((item) => holeIds.has(item.design_hole_id)),
        as_charged_holes: document.as_charged_holes.filter((item) => holeIds.has(item.design_hole_id)),
        as_fired_holes: document.as_fired_holes.filter((item) => holeIds.has(item.design_hole_id)),
        ...pruned,
        network: holes.length === document.holes.length ? pruned.network : staleNetwork(pruned.network),
      };
    }
    case "SET_CHARGE_RULES":
      return { ...document, charge_rules: { ...document.charge_rules, ...action.rules } };
    case "SET_LOADS":
      return { ...document, loads: action.loads };
    case "SET_NETWORK":
      return { ...document, network: normalizeNetwork(action.network) };
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
    case "SET_RECEPTORS":
      return { ...document, receptors: action.receptors };
    case "UPSERT_RECEPTOR": {
      const exists = document.receptors.some((item) => item.id === action.receptor.id);
      return {
        ...document,
        receptors: exists
          ? document.receptors.map((item) => (item.id === action.receptor.id ? action.receptor : item))
          : [...document.receptors, action.receptor],
      };
    }
    case "DELETE_RECEPTOR":
      return {
        ...document,
        receptors: document.receptors.filter((item) => item.id !== action.id),
        vibration_measurements: document.vibration_measurements.filter((item) => item.receptor_id !== action.id),
      };
    case "SET_VIBRATION_MODELS":
      return { ...document, vibration_models: action.models };
    case "UPSERT_VIBRATION_MODEL": {
      const exists = document.vibration_models.some((item) => item.id === action.model.id);
      return {
        ...document,
        vibration_models: exists
          ? document.vibration_models.map((item) => (item.id === action.model.id ? action.model : item))
          : [...document.vibration_models, action.model],
      };
    }
    case "SET_VIBRATION_MEASUREMENTS":
      return { ...document, vibration_measurements: action.measurements };
    case "UPSERT_MEASUREMENT": {
      const exists = document.vibration_measurements.some((item) => item.id === action.measurement.id);
      return {
        ...document,
        vibration_measurements: exists
          ? document.vibration_measurements.map((item) => (item.id === action.measurement.id ? action.measurement : item))
          : [...document.vibration_measurements, action.measurement],
      };
    }
    case "DELETE_MEASUREMENT":
      return {
        ...document,
        vibration_measurements: document.vibration_measurements.filter((item) => item.id !== action.id),
      };
    case "SET_AS_DRILLED":
      return { ...document, as_drilled_holes: action.holes };
    case "UPSERT_AS_DRILLED": {
      const exists = document.as_drilled_holes.some((item) => item.design_hole_id === action.hole.design_hole_id);
      return {
        ...document,
        as_drilled_holes: exists
          ? document.as_drilled_holes.map((item) => (item.design_hole_id === action.hole.design_hole_id ? action.hole : item))
          : [...document.as_drilled_holes, action.hole],
      };
    }
    case "DELETE_AS_DRILLED":
      return {
        ...document,
        as_drilled_holes: document.as_drilled_holes.filter((item) => item.design_hole_id !== action.designHoleId),
      };
    case "SET_AS_CHARGED":
      return { ...document, as_charged_holes: action.holes };
    case "UPSERT_AS_CHARGED": {
      const exists = document.as_charged_holes.some((item) => item.design_hole_id === action.hole.design_hole_id);
      return {
        ...document,
        as_charged_holes: exists
          ? document.as_charged_holes.map((item) => (item.design_hole_id === action.hole.design_hole_id ? action.hole : item))
          : [...document.as_charged_holes, action.hole],
      };
    }
    case "DELETE_AS_CHARGED":
      return {
        ...document,
        as_charged_holes: document.as_charged_holes.filter((item) => item.design_hole_id !== action.designHoleId),
      };
    case "SET_AS_FIRED":
      return { ...document, as_fired_holes: action.holes };
    case "UPSERT_AS_FIRED": {
      const exists = document.as_fired_holes.some((item) => item.design_hole_id === action.hole.design_hole_id);
      return {
        ...document,
        as_fired_holes: exists
          ? document.as_fired_holes.map((item) => (item.design_hole_id === action.hole.design_hole_id ? action.hole : item))
          : [...document.as_fired_holes, action.hole],
      };
    }
    case "DELETE_AS_FIRED":
      return {
        ...document,
        as_fired_holes: document.as_fired_holes.filter((item) => item.design_hole_id !== action.designHoleId),
      };
    case "SET_BLAST_RESULT":
      return { ...document, blast_result: action.result };
    case "SET_HOLE_GEOLOGY": {
      const byId = new Map(action.holes.map((h) => [h.id, h]));
      return {
        ...document,
        holes: document.holes.map((h) => {
          const next = byId.get(h.id);
          // Ось сменилась, пока пересекалась геология (пересчёт по кровле,
          // правка) — интервалы старой оси не ставим.
          if (!next || !sameAxis(h, next)) return h;
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
  "SET_ROCK_NAME",
  "SET_CONTOUR_VERTICES",
  "APPLY_CAD_CONTOUR",
  "TOGGLE_FREE_FACE",
  "SET_BENCH",
  "SET_TOE_SOURCE",
  "SET_SURFACE",
  "CLEAR_SURFACE",
  "SET_HOLES",
  "APPLY_LAYOUT",
  "APPLY_SURVEY",
  "RENUMBER_HOLES",
  "MOVE_HOLES",
  "RETURN_TO_NODE",
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
  "SET_RECEPTORS",
  "UPSERT_RECEPTOR",
  "DELETE_RECEPTOR",
  "SET_VIBRATION_MODELS",
  "UPSERT_VIBRATION_MODEL",
  "SET_VIBRATION_MEASUREMENTS",
  "UPSERT_MEASUREMENT",
  "DELETE_MEASUREMENT",
  "SET_AS_DRILLED",
  "UPSERT_AS_DRILLED",
  "DELETE_AS_DRILLED",
  "SET_AS_CHARGED",
  "UPSERT_AS_CHARGED",
  "DELETE_AS_CHARGED",
  "SET_AS_FIRED",
  "UPSERT_AS_FIRED",
  "DELETE_AS_FIRED",
];

/** Сеть построена шаблоном, не правлена и её можно пересчитать без формы. */
function retiesItself(document: BlastDesign): boolean {
  const network = normalizeNetwork(document.network);
  return !isNetworkEmpty(network) && networkOrigin(network) === "template" && retieRequest(network) !== null;
}

/**
 * Действия со скважинами, после которых сеть шаблона пересчитывается сама
 * (TASK-017, PR 3 — сдвиг; PR 5 — добавление, удаление, исключение, вид).
 * Пересчёт — только если действие пометило сеть устаревшей.
 */
const HOLE_SET_ACTIONS: ReadonlySet<DesignAction["type"]> = new Set([
  "MOVE_HOLES",
  "RETURN_TO_NODE",
  "ADD_HOLE",
  "DELETE_HOLES",
  "SET_HOLES_ENABLED",
  "UPDATE_HOLE",
  "APPLY_SURVEY",
]);

export function designReducer(state: DesignState, action: DesignAction): DesignState {
  const next = reduceState(state, action);
  if (next === state) return next;
  if (
    HOLE_SET_ACTIONS.has(action.type)
    && next.present.network !== state.present.network
    && isGeometryStale(normalizeNetwork(next.present.network))
    && retiesItself(next.present)
  ) {
    return { ...next, autoRetie: { present: next.present, series: action.type === "MOVE_HOLES" && action.series !== undefined } };
  }
  if ((action.type === "RECOMPUTE_HOLES" || action.type === "SAVED") && state.autoRetie?.present === state.present) {
    // Пересчёт по кровле приходит сам после сдвига, сохранение правок не
    // меняет — пересчёт коммутации всё ещё нужен.
    return { ...next, autoRetie: { ...state.autoRetie, present: next.present } };
  }
  return next;
}

function reduceState(state: DesignState, action: DesignAction): DesignState {
  if ((action.type === "LOAD" || action.type === "SAVED") && action.base && action.base !== state.saved) {
    // Пока шёл запрос, открыли другой паспорт: ответ о прежнем ему не принадлежит.
    return state;
  }
  if (action.type === "LOAD") {
    // Иначе Ctrl+Z вернул бы на экран прежний паспорт с его design_id, и
    // «Сохранить» записало бы его старое состояние.
    return initDesignState(normalizeDesign(action.design));
  }
  if (action.type === "SAVED") {
    // Отмена после сохранения возвращает правку, но не прежние служебные поля:
    // без этого первое сохранение нового паспорта и отмена дали бы пустой
    // design_id, и следующее «Сохранить» создало бы копию.
    const present = normalizeDesign(action.design);
    const server = serverFields(present);
    const rebase = (design: BlastDesign): BlastDesign => ({ ...design, ...server });
    return { past: state.past.map(rebase), present, future: state.future.map(rebase), saved: present };
  }
  if (action.type === "UNDO") {
    if (state.past.length === 0) return state;
    const previous = state.past[state.past.length - 1];
    return {
      ...state,
      past: state.past.slice(0, -1),
      present: previous,
      future: [state.present, ...state.future].slice(0, HISTORY_LIMIT),
      // Отмена может вернуть ровно тот документ, которым кончилась серия
      // стрелок: следующее нажатие — новая запись, а не продолжение.
      moveSeries: undefined,
    };
  }
  if (action.type === "RETIE_NETWORK") {
    // Пока шёл пересчёт, документ сменился (сдвиг, отмена, другая правка):
    // сеть посчитана не для него.
    if (action.base !== state.present) return state;
    const present = { ...state.present, network: normalizeNetwork(action.network) };
    if (action.merge) return { ...state, present, moveSeries: undefined };
    return { ...state, past: [...state.past, state.present].slice(-HISTORY_LIMIT), present, future: [], moveSeries: undefined };
  }
  if (action.type === "REDO") {
    if (state.future.length === 0) return state;
    const [next, ...rest] = state.future;
    return { ...state, past: [...state.past, state.present].slice(-HISTORY_LIMIT), present: next, future: rest, moveSeries: undefined };
  }

  const current = state.present;
  const nextPresent = reduceDocument(current, action);
  if (nextPresent === state.present) return state;

  if (action.type === "MOVE_HOLES" && action.series !== undefined) {
    const series = state.moveSeries;
    const ids = [...action.ids].sort().join("\n");
    const moveSeries = { at: action.series, present: nextPresent, ids };
    if (series && series.present === current && series.ids === ids && action.series - series.at <= MOVE_SERIES_GAP_MS) {
      // Продолжение серии стрелок: шаг истории уже создан первым нажатием.
      return { ...state, present: nextPresent, future: [], moveSeries };
    }
    return {
      ...state,
      past: [...state.past, current].slice(-HISTORY_LIMIT),
      present: nextPresent,
      future: [],
      moveSeries,
    };
  }

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
    if (action.type === "RECOMPUTE_HOLES" && state.moveSeries?.present === current) {
      // Пересчёт по кровле и подошве приходит сам после нажатия стрелки —
      // это не правка пользователя, и серия стрелок им не рвётся.
      return { ...state, present: nextPresent, moveSeries: { ...state.moveSeries, present: nextPresent } };
    }
    return { ...state, present: nextPresent };
  }

  return {
    ...state,
    past: [...state.past, current].slice(-HISTORY_LIMIT),
    present: nextPresent,
    future: [],
  };
}
