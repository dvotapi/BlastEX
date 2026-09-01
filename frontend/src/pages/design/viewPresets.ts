import type { WorkflowStageId } from "../../lib/lifecycle";
import type { MapLayerVisibility } from "./MapLegend";

/** Предустановки карты для этапов проектирования и проверки. */
export type ViewPresetId =
  | "survey"
  | "pattern"
  | "charge"
  | "network"
  | "timing"
  | "actual"
  | "review";

export type ExtendedLayerId =
  | "fill"
  | "crest"
  | "toe"
  | "face"
  | "holes"
  | "labels"
  | "network"
  | "health"
  | "dimensions"
  | "isolines"
  | "receptors"
  | "movement"
  | "asDrilled"
  | "domains"
  | "throw";

export type ExtendedMapLayers = Record<ExtendedLayerId, boolean>;

export type LabelField = "id" | "row" | "time" | "charge" | "none";
export type ColorMode = "kind" | "charge" | "map" | "health";
export type CameraMode3d = "collar" | "shaft" | "toe";

export type DesignViewState = {
  preset: ViewPresetId;
  layers: ExtendedMapLayers;
  labelField: LabelField;
  colorMode: ColorMode;
  showHealth: boolean;
  showMeasure: boolean;
  cameraMode3d: CameraMode3d;
};

export type LabelPlacement = {
  id: string;
  x: number;
  y: number;
  text: string;
  hidden?: boolean;
};

export const VIEW_PRESET_LABELS: Record<ViewPresetId, string> = {
  survey: "Съёмка",
  pattern: "Сетка",
  charge: "Заряд",
  network: "Связь",
  timing: "Тайминг",
  actual: "Факт",
  review: "Проверка",
};

export const LAYER_LABELS: Record<ExtendedLayerId, string> = {
  fill: "Заливка контура",
  crest: "Верхняя бровка",
  toe: "Нижняя бровка",
  face: "Откос",
  holes: "Скважины",
  labels: "Подписи",
  network: "Сеть инициирования",
  health: "Диагностика",
  dimensions: "Размеры при перетаскивании",
  isolines: "Изолинии времени",
  receptors: "Рецепторы",
  movement: "Векторы смещения",
  asDrilled: "Факт бурения",
  domains: "Геологические регионы",
  throw: "Направление выброса",
};

export const ALL_LAYER_IDS: ExtendedLayerId[] = Object.keys(LAYER_LABELS) as ExtendedLayerId[];

const DEFAULT_LAYERS: ExtendedMapLayers = {
  fill: true,
  crest: true,
  toe: true,
  face: true,
  holes: true,
  labels: true,
  network: false,
  health: false,
  dimensions: true,
  isolines: false,
  receptors: false,
  movement: false,
  asDrilled: false,
  domains: true,
  throw: false,
};

const PRESET_OVERRIDES: Record<ViewPresetId, Partial<ExtendedMapLayers> & Partial<Pick<DesignViewState, "labelField" | "colorMode" | "showHealth">>> = {
  survey: {
    labels: false,
    network: false,
    health: false,
    isolines: false,
    asDrilled: false,
    movement: false,
    throw: false,
    labelField: "none",
    colorMode: "kind",
    showHealth: false,
  },
  pattern: {
    labels: true,
    dimensions: true,
    network: false,
    health: false,
    isolines: false,
    labelField: "row",
    colorMode: "kind",
    showHealth: false,
  },
  charge: {
    labels: true,
    network: false,
    health: false,
    labelField: "charge",
    colorMode: "charge",
    showHealth: false,
  },
  network: {
    labels: true,
    network: true,
    health: false,
    isolines: false,
    labelField: "id",
    colorMode: "kind",
    showHealth: false,
  },
  timing: {
    labels: true,
    network: true,
    isolines: true,
    health: false,
    labelField: "time",
    colorMode: "map",
    showHealth: false,
  },
  actual: {
    labels: true,
    asDrilled: true,
    movement: true,
    throw: true,
    health: false,
    labelField: "id",
    colorMode: "kind",
    showHealth: false,
  },
  review: {
    labels: true,
    network: true,
    health: true,
    dimensions: true,
    isolines: true,
    receptors: true,
    labelField: "id",
    colorMode: "health",
    showHealth: true,
  },
};

const STAGE_PRESET: Partial<Record<WorkflowStageId, ViewPresetId>> = {
  survey: "survey",
  geology: "survey",
  pattern: "pattern",
  charge: "charge",
  timing: "timing",
  simulation: "timing",
  execution: "actual",
  intelligence: "review",
  scenarios: "review",
  report: "review",
};

export function defaultLayers(): ExtendedMapLayers {
  return { ...DEFAULT_LAYERS };
}

export function defaultDesignViewState(stage?: WorkflowStageId): DesignViewState {
  const preset = stage ? stageDefaultPreset(stage) : "survey";
  return applyViewPreset(preset);
}

export function stageDefaultPreset(stage: WorkflowStageId): ViewPresetId {
  return STAGE_PRESET[stage] ?? "survey";
}

export function applyViewPreset(preset: ViewPresetId, current?: Partial<DesignViewState>): DesignViewState {
  const override = PRESET_OVERRIDES[preset];
  const layers = { ...DEFAULT_LAYERS, ...current?.layers, ...override };
  return {
    preset,
    layers,
    labelField: override.labelField ?? current?.labelField ?? "id",
    colorMode: override.colorMode ?? current?.colorMode ?? "kind",
    showHealth: override.showHealth ?? current?.showHealth ?? false,
    showMeasure: current?.showMeasure ?? false,
    cameraMode3d: current?.cameraMode3d ?? "collar",
  };
}

/** Совместимость со старым MapLegend — только слои контура. */
export function contourLayersFromView(layers: ExtendedMapLayers): MapLayerVisibility {
  return {
    fill: layers.fill,
    crest: layers.crest,
    toe: layers.toe,
    face: layers.face,
    holes: layers.holes,
  };
}

export function filterLayers(query: string): ExtendedLayerId[] {
  const q = query.trim().toLowerCase();
  if (!q) return ALL_LAYER_IDS;
  return ALL_LAYER_IDS.filter((id) => LAYER_LABELS[id].toLowerCase().includes(q));
}

/** Скрывает подписи, которые перекрывают друг друга на экране. */
export function resolveLabelCollisions(labels: LabelPlacement[], minGap = 14): LabelPlacement[] {
  if (labels.length <= 1) return labels.map((item) => ({ ...item }));
  const sorted = [...labels].sort((a, b) => a.y - b.y || a.x - b.x);
  const kept: LabelPlacement[] = [];
  for (const label of sorted) {
    const overlaps = kept.some(
      (other) => !other.hidden && Math.hypot(label.x - other.x, label.y - other.y) < minGap,
    );
    kept.push(overlaps ? { ...label, hidden: true } : { ...label });
  }
  return kept;
}

export function patchDesignView(
  state: DesignViewState,
  patch: Partial<DesignViewState> & { layers?: Partial<ExtendedMapLayers> },
): DesignViewState {
  return {
    ...state,
    ...patch,
    layers: patch.layers ? { ...state.layers, ...patch.layers } : state.layers,
  };
}
