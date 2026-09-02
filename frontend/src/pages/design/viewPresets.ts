import type { WorkflowStageId } from "../../lib/lifecycle";

export type ViewPresetId =
  | "survey"
  | "pattern"
  | "charge"
  | "network"
  | "timing"
  | "actual"
  | "review";

export type MapLabelField =
  | "none"
  | "id"
  | "delay_ms"
  | "charge_kg"
  | "depth_m"
  | "diameter_mm"
  | "angle_deg";

export type MapColorMode = "kind" | "charge_kg" | "delay_ms" | "health" | "as_drilled";

export type CameraMode3d = "collar" | "shaft" | "toe";

export type LayerId =
  | "terrain"
  | "contour_fill"
  | "contour_crest"
  | "contour_toe"
  | "contour_face"
  | "holes"
  | "labels"
  | "network"
  | "isolines"
  | "throw_direction"
  | "actual"
  | "health";

export type LayerVisibility = Record<LayerId, boolean>;

export type DesignViewState = {
  preset: ViewPresetId;
  layers: LayerVisibility;
  labelField: MapLabelField;
  colorMode: MapColorMode;
  cameraMode3d: CameraMode3d;
  measurePhase: "idle" | "measuring" | "result";
  presetLocked: boolean;
};

export type LayerGroup = "contour" | "holes" | "analysis" | "execution";

export type LayerDef = {
  id: LayerId;
  label: string;
  group: LayerGroup;
  swatch: string;
  keywords: string[];
};

export const VIEW_PRESET_LABELS: Record<ViewPresetId, string> = {
  survey: "Съёмка",
  pattern: "Сетка",
  charge: "Заряд",
  network: "Сеть",
  timing: "Тайминг",
  actual: "Факт",
  review: "Проверка",
};

export const LABEL_FIELD_LABELS: Record<MapLabelField, string> = {
  none: "без подписи",
  id: "номер",
  delay_ms: "время",
  charge_kg: "масса ВВ",
  depth_m: "глубина",
  diameter_mm: "диаметр",
  angle_deg: "угол",
};

export const COLOR_MODE_LABELS: Record<MapColorMode, string> = {
  kind: "тип скважины",
  charge_kg: "масса заряда",
  delay_ms: "время взрыва",
  health: "замечания",
  as_drilled: "факт бурения",
};

export const CAMERA_MODE_LABELS: Record<CameraMode3d, string> = {
  collar: "Устье",
  shaft: "Ствол",
  toe: "Подошва",
};

export const LAYER_DEFS: LayerDef[] = [
  { id: "terrain", label: "Рельеф / каркас", group: "contour", swatch: "terrain", keywords: ["рельеф", "каркас", "поверхность"] },
  { id: "contour_fill", label: "Заливка контура", group: "contour", swatch: "fill", keywords: ["заливка", "контур"] },
  { id: "contour_crest", label: "Верхняя бровка", group: "contour", swatch: "crest", keywords: ["бровка", "верх", "кровля"] },
  { id: "contour_toe", label: "Нижняя бровка", group: "contour", swatch: "toe", keywords: ["подошва", "низ"] },
  { id: "contour_face", label: "Откос", group: "contour", swatch: "face", keywords: ["откос", "открытый"] },
  { id: "holes", label: "Скважины", group: "holes", swatch: "holes", keywords: ["скважины", "ствол"] },
  { id: "labels", label: "Подписи", group: "holes", swatch: "labels", keywords: ["подпись", "номер", "азимут", "глубина", "заряд", "время"] },
  { id: "network", label: "Сеть инициирования", group: "analysis", swatch: "network", keywords: ["сеть", "связь", "нси"] },
  { id: "isolines", label: "Изолинии времени", group: "analysis", swatch: "isolines", keywords: ["изолинии", "время", "тайминг"] },
  { id: "throw_direction", label: "Направление выброса", group: "analysis", swatch: "throw", keywords: ["выброс", "инициация", "угол"] },
  { id: "actual", label: "Факт бурения / зарядки", group: "execution", swatch: "actual", keywords: ["факт", "бурение", "зарядка"] },
  { id: "health", label: "Замечания", group: "execution", swatch: "health", keywords: ["замечания", "проверка", "ошибка"] },
];

const LAYER_GROUP_LABELS: Record<LayerGroup, string> = {
  contour: "Контур",
  holes: "Скважины",
  analysis: "Анализ",
  execution: "Исполнение",
};

export const LABEL_MIN_SCALE_PX_PER_M = 5.5;

type PresetTemplate = Pick<DesignViewState, "layers" | "labelField" | "colorMode">;

const ALL_LAYERS_ON: LayerVisibility = Object.fromEntries(LAYER_DEFS.map((d) => [d.id, true])) as LayerVisibility;

function baseLayers(overrides: Partial<LayerVisibility>): LayerVisibility {
  return { ...ALL_LAYERS_ON, ...overrides };
}

const PRESET_TEMPLATES: Record<ViewPresetId, PresetTemplate> = {
  survey: {
    layers: baseLayers({
      network: false,
      isolines: false,
      throw_direction: false,
      actual: false,
      health: false,
    }),
    labelField: "id",
    colorMode: "kind",
  },
  pattern: {
    layers: baseLayers({
      terrain: false,
      network: false,
      isolines: false,
      throw_direction: false,
      actual: false,
      health: false,
    }),
    labelField: "id",
    colorMode: "kind",
  },
  charge: {
    layers: baseLayers({
      terrain: false,
      network: false,
      isolines: false,
      throw_direction: false,
      actual: false,
      health: false,
    }),
    labelField: "charge_kg",
    colorMode: "charge_kg",
  },
  network: {
    layers: baseLayers({
      terrain: false,
      isolines: false,
      throw_direction: false,
      actual: false,
      health: false,
    }),
    labelField: "id",
    colorMode: "kind",
  },
  timing: {
    layers: baseLayers({
      terrain: false,
      actual: false,
      health: false,
    }),
    labelField: "delay_ms",
    colorMode: "delay_ms",
  },
  actual: {
    layers: baseLayers({
      network: false,
      isolines: false,
      throw_direction: false,
      health: false,
    }),
    labelField: "id",
    colorMode: "as_drilled",
  },
  review: {
    layers: baseLayers({
      terrain: false,
      isolines: false,
      throw_direction: false,
      actual: false,
    }),
    labelField: "id",
    colorMode: "health",
  },
};

export const STAGE_DEFAULT_PRESET: Partial<Record<WorkflowStageId, ViewPresetId>> = {
  survey: "survey",
  geology: "survey",
  pattern: "pattern",
  charge: "charge",
  timing: "network",
  simulation: "timing",
  execution: "actual",
  intelligence: "review",
  scenarios: "review",
  report: "survey",
};

export function defaultDesignViewState(preset: ViewPresetId = "survey"): DesignViewState {
  const template = PRESET_TEMPLATES[preset];
  return {
    preset,
    layers: { ...template.layers },
    labelField: template.labelField,
    colorMode: template.colorMode,
    cameraMode3d: "collar",
    measurePhase: "idle",
    presetLocked: false,
  };
}

export function applyViewPreset(preset: ViewPresetId, locked = true): DesignViewState {
  const next = defaultDesignViewState(preset);
  next.presetLocked = locked;
  return next;
}

export function applyPresetToState(state: DesignViewState, preset: ViewPresetId, locked = true): DesignViewState {
  const template = PRESET_TEMPLATES[preset];
  return {
    ...state,
    preset,
    layers: { ...template.layers },
    labelField: template.labelField,
    colorMode: template.colorMode,
    presetLocked: locked,
  };
}

export function resetLayersToPreset(state: DesignViewState): DesignViewState {
  const template = PRESET_TEMPLATES[state.preset];
  return { ...state, layers: { ...template.layers }, labelField: template.labelField, colorMode: template.colorMode };
}

export function stageDefaultPreset(stage: WorkflowStageId): ViewPresetId {
  return STAGE_DEFAULT_PRESET[stage] ?? "survey";
}

export function layerGroups(query: string): Array<{ group: LayerGroup; label: string; items: LayerDef[] }> {
  const q = query.trim().toLowerCase();
  const filtered = q
    ? LAYER_DEFS.filter((item) => item.label.toLowerCase().includes(q) || item.keywords.some((k) => k.includes(q)))
    : LAYER_DEFS;
  const groups = new Map<LayerGroup, LayerDef[]>();
  for (const item of filtered) {
    const list = groups.get(item.group) ?? [];
    list.push(item);
    groups.set(item.group, list);
  }
  return Array.from(groups.entries()).map(([group, items]) => ({
    group,
    label: LAYER_GROUP_LABELS[group],
    items,
  }));
}

/** Legacy contour visibility for PlanCanvas. */
export function contourLayersFromView(layers: LayerVisibility): {
  fill: boolean;
  crest: boolean;
  toe: boolean;
  face: boolean;
  holes: boolean;
} {
  return {
    fill: layers.contour_fill,
    crest: layers.contour_crest,
    toe: layers.contour_toe,
    face: layers.contour_face,
    holes: layers.holes,
  };
}

export type LabelBox = {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
  priority: number;
};

function rectsOverlap(a: LabelBox, b: LabelBox): boolean {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
}

/** Greedy anti-collision: higher priority labels win. */
export function visibleLabelIds(boxes: LabelBox[]): Set<string> {
  const sorted = [...boxes].sort((a, b) => b.priority - a.priority);
  const placed: LabelBox[] = [];
  const visible = new Set<string>();
  for (const box of sorted) {
    if (placed.some((p) => rectsOverlap(box, p))) continue;
    visible.add(box.id);
    placed.push(box);
  }
  return visible;
}

export function labelsVisibleAtScale(scalePxPerM: number): boolean {
  return scalePxPerM >= LABEL_MIN_SCALE_PX_PER_M;
}

/** Радиус маркера скважины на плане, px.
 *
 * Физический радиус (диаметр × масштаб) при обычных масштабах меньше пикселя,
 * поэтому маркер держит минимальный размер. Но фиксированные 5 px при мелком
 * масштабе сливают сетку 5 × 4 м в сплошное пятно, так что минимум ужимается
 * вместе с масштабом: 2,5 px на обзоре блока, 5 px там, где уже видны подписи.
 */
export function holeMarkerRadiusPx(diameterMm: number, scalePxPerM: number, selected = false): number {
  const physical = ((diameterMm / 1000) * scalePxPerM) / 2;
  const floor = Math.min(5, Math.max(2.5, scalePxPerM * 0.8));
  return Math.max(selected ? floor + 1.5 : floor, physical);
}
