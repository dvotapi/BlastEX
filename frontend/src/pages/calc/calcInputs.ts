/**
 * Настройки листа «Расчёт» за объектом работ: сбор с листа, применение к листу
 * и сравнение. Модуль чистый — ни запросов, ни React: сервер настройки только
 * хранит, а вся проверка значений живёт здесь, потому что границы полей знает
 * форма, а не API.
 */

/** Поля панели «Вариант 1/2» (схема заряда скважины). */
export type PanelInputs = {
  explosive_key: string;
  undercharge_m: number;
  intermediate_detonators_per_hole: number;
  nsi_per_hole: number;
  nsi_length_1_m: number;
  nsi_length_2_m: number;
  detonator_delay_ms: number;
};

/** То, что уходит на сервер и приходит обратно. Ключи — как в API (snake_case). */
export type CalcInputs = {
  version: 1;
  rock_name: string;
  explosive_key: string;
  lump_size_mm: number;
  bench_height_m: number;
  overdrill_m: number;
  oversize_coeff: number;
  spacing_coeff: number;
  oversize_threshold_pct: number;
  selected_crowns_mm: number[];
  selected_crown_mm: number | null;
  block_volume_m3: number;
  additional_holes_pct: number;
  panels: { left: PanelInputs; right: PanelInputs };
};

/** Состояние листа в терминах формы (то, что лежит в `useState` компонента). */
export type SheetState = {
  rockName: string;
  explosiveKey: string;
  lumpSizeMm: number;
  benchHeightM: number;
  overdrillM: number;
  oversizeCoeff: number;
  spacingCoeff: number;
  oversizeThresholdPct: number;
  selectedCrownsMm: number[];
  selectedCrownMm: number | null;
  blockVolumeM3: number;
  additionalHolesPct: number;
  panels: { left: PanelInputs; right: PanelInputs };
};

/** Справочники, по которым проверяются сохранённые значения. */
export type CalcInputsCatalogs = {
  rocks: string[];
  explosiveKeys: string[];
  crowns: number[];
};

/** Задержка автосохранения: пишем через 800 мс после последнего изменения. */
export const AUTOSAVE_DELAY_MS = 800;

export const DEFAULT_EXPLOSIVE_1 = "ПВВ Гранулит-РП";
export const DEFAULT_EXPLOSIVE_2 = "ПЭВВ ЭВЕРСИН Э-100";
export const DEFAULT_UNDERCHARGE_1_M = 3.1;
export const DEFAULT_UNDERCHARGE_2_M = 2.0;
export const NSI_LENGTH_DEFAULT_1 = 12.0;
export const NSI_LENGTH_DEFAULT_2 = 6.0;
export const DETONATOR_DELAY_DEFAULT = 500;

/** Границы полей формы: сохранённое значение вне них обрезается, а не ломает ввод. */
const BOUNDS = {
  lumpSizeMm: { min: 100, max: 1200, fallback: 400 },
  benchHeightM: { min: 5, max: 25, fallback: 10 },
  overdrillM: { min: 0, max: 3, fallback: 1 },
  oversizeCoeff: { min: 1, max: 1.15, fallback: 1.05 },
  spacingCoeff: { min: 1, max: 2, fallback: 1.25 },
  oversizeThresholdPct: { min: 1, max: 15, fallback: 5 },
  blockVolumeM3: { min: 1000, max: Number.POSITIVE_INFINITY, fallback: 30_000 },
  additionalHolesPct: { min: 0, max: 20, fallback: 3.0 },
} as const;

/** Недозаряд не может быть глубже скважины: тот же предел, что у ползунка
 * панели (`depthM` — высота уступа с перебуром). */
export function maxUnderchargeM(depthM: number): number {
  return Math.max(0, depthM - 0.5);
}

export function defaultPanelInputs(explosiveKey: string, underchargeM: number): PanelInputs {
  return {
    explosive_key: explosiveKey,
    undercharge_m: underchargeM,
    intermediate_detonators_per_hole: 1,
    nsi_per_hole: 1,
    nsi_length_1_m: NSI_LENGTH_DEFAULT_1,
    nsi_length_2_m: NSI_LENGTH_DEFAULT_2,
    detonator_delay_ms: DETONATOR_DELAY_DEFAULT,
  };
}

/** Лист без сохранённых настроек: умолчания справочников и все диаметры. */
export function defaultCalcSheet(
  catalogs: CalcInputsCatalogs,
  defaults: { rockName: string; explosiveKey: string },
): SheetState {
  const benchHeightM = BOUNDS.benchHeightM.fallback;
  const overdrillM = BOUNDS.overdrillM.fallback;
  const limit = maxUnderchargeM(benchHeightM + overdrillM);
  return {
    rockName: defaults.rockName,
    explosiveKey: defaults.explosiveKey,
    lumpSizeMm: BOUNDS.lumpSizeMm.fallback,
    benchHeightM,
    overdrillM,
    oversizeCoeff: BOUNDS.oversizeCoeff.fallback,
    spacingCoeff: BOUNDS.spacingCoeff.fallback,
    oversizeThresholdPct: BOUNDS.oversizeThresholdPct.fallback,
    selectedCrownsMm: [...catalogs.crowns],
    selectedCrownMm: null,
    blockVolumeM3: BOUNDS.blockVolumeM3.fallback,
    additionalHolesPct: BOUNDS.additionalHolesPct.fallback,
    panels: {
      left: defaultPanelInputs(DEFAULT_EXPLOSIVE_1, Math.min(DEFAULT_UNDERCHARGE_1_M, limit)),
      right: defaultPanelInputs(DEFAULT_EXPLOSIVE_2, Math.min(DEFAULT_UNDERCHARGE_2_M, limit)),
    },
  };
}

export function collectCalcInputs(sheet: SheetState): CalcInputs {
  return {
    version: 1,
    rock_name: sheet.rockName,
    explosive_key: sheet.explosiveKey,
    lump_size_mm: sheet.lumpSizeMm,
    bench_height_m: sheet.benchHeightM,
    overdrill_m: sheet.overdrillM,
    oversize_coeff: sheet.oversizeCoeff,
    spacing_coeff: sheet.spacingCoeff,
    oversize_threshold_pct: sheet.oversizeThresholdPct,
    selected_crowns_mm: [...sheet.selectedCrownsMm],
    selected_crown_mm: sheet.selectedCrownMm,
    block_volume_m3: sheet.blockVolumeM3,
    additional_holes_pct: sheet.additionalHolesPct,
    panels: { left: { ...sheet.panels.left }, right: { ...sheet.panels.right } },
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function clamped(value: unknown, bounds: { min: number; max: number; fallback: number }): number {
  if (typeof value !== "number" || !Number.isFinite(value)) return bounds.fallback;
  return Math.min(bounds.max, Math.max(bounds.min, value));
}

function fromCatalog(value: unknown, options: string[], fallback: string): string {
  if (typeof value === "string" && options.includes(value)) return value;
  return options[0] ?? fallback;
}

function positive(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) && value > 0 ? value : fallback;
}

function oneOrTwo(value: unknown, fallback: number): number {
  return value === 1 || value === 2 ? value : fallback;
}

function applyPanelInputs(
  raw: unknown,
  catalogs: CalcInputsCatalogs,
  fallback: PanelInputs,
  underchargeLimit: number,
): PanelInputs {
  const source = isRecord(raw) ? raw : {};
  return {
    explosive_key: fromCatalog(source.explosive_key, catalogs.explosiveKeys, fallback.explosive_key),
    undercharge_m: clamped(source.undercharge_m, {
      min: 0,
      max: underchargeLimit,
      fallback: Math.min(fallback.undercharge_m, underchargeLimit),
    }),
    intermediate_detonators_per_hole: oneOrTwo(
      source.intermediate_detonators_per_hole,
      fallback.intermediate_detonators_per_hole,
    ),
    nsi_per_hole: oneOrTwo(source.nsi_per_hole, fallback.nsi_per_hole),
    nsi_length_1_m: positive(source.nsi_length_1_m, fallback.nsi_length_1_m),
    nsi_length_2_m: positive(source.nsi_length_2_m, fallback.nsi_length_2_m),
    detonator_delay_ms: positive(source.detonator_delay_ms, fallback.detonator_delay_ms),
  };
}

/**
 * Сохранённые настройки → состояние листа. `null` — если пришло не то, что мы
 * писали (другая версия формата, мусор): в этом случае лист остаётся на
 * умолчаниях. Неизвестные порода, ВВ и диаметр заменяются первым доступным,
 * числа вне диапазона обрезаются по границам полей.
 */
export function applyCalcInputs(raw: unknown, catalogs: CalcInputsCatalogs): SheetState | null {
  if (!isRecord(raw)) return null;
  if (raw.version !== 1) return null;
  if (typeof raw.rock_name !== "string") return null;
  if (!isRecord(raw.panels) || !isRecord(raw.panels.left) || !isRecord(raw.panels.right)) return null;

  const benchHeightM = clamped(raw.bench_height_m, BOUNDS.benchHeightM);
  const overdrillM = clamped(raw.overdrill_m, BOUNDS.overdrillM);
  const underchargeLimit = maxUnderchargeM(benchHeightM + overdrillM);

  const savedCrowns = Array.isArray(raw.selected_crowns_mm) ? raw.selected_crowns_mm : [];
  const known = savedCrowns.filter(
    (value, index): value is number =>
      typeof value === "number" && catalogs.crowns.includes(value) && savedCrowns.indexOf(value) === index,
  );
  const selectedCrownsMm = known.length ? known : catalogs.crowns.slice(0, 1);
  const savedCrown = raw.selected_crown_mm;
  const selectedCrownMm =
    typeof savedCrown === "number" && selectedCrownsMm.includes(savedCrown) ? savedCrown : null;

  const defaults = defaultCalcSheet(catalogs, { rockName: "", explosiveKey: "" });
  return {
    rockName: fromCatalog(raw.rock_name, catalogs.rocks, raw.rock_name),
    explosiveKey: fromCatalog(raw.explosive_key, catalogs.explosiveKeys, ""),
    lumpSizeMm: clamped(raw.lump_size_mm, BOUNDS.lumpSizeMm),
    benchHeightM,
    overdrillM,
    oversizeCoeff: clamped(raw.oversize_coeff, BOUNDS.oversizeCoeff),
    spacingCoeff: clamped(raw.spacing_coeff, BOUNDS.spacingCoeff),
    oversizeThresholdPct: clamped(raw.oversize_threshold_pct, BOUNDS.oversizeThresholdPct),
    selectedCrownsMm,
    selectedCrownMm,
    blockVolumeM3: clamped(raw.block_volume_m3, BOUNDS.blockVolumeM3),
    additionalHolesPct: clamped(raw.additional_holes_pct, BOUNDS.additionalHolesPct),
    panels: {
      left: applyPanelInputs(raw.panels.left, catalogs, defaults.panels.left, underchargeLimit),
      right: applyPanelInputs(raw.panels.right, catalogs, defaults.panels.right, underchargeLimit),
    },
  };
}

/** Сериализация с упорядоченными ключами: сравнение не должно зависеть от их порядка. */
function stableJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`;
  if (isRecord(value)) {
    const keys = Object.keys(value).sort();
    return `{${keys.map((key) => `${JSON.stringify(key)}:${stableJson(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value) ?? "null";
}

export function calcInputsEqual(a: CalcInputs | null, b: CalcInputs | null): boolean {
  if (a === b) return true;
  if (!a || !b) return false;
  return stableJson(a) === stableJson(b);
}

export function panelInputsEqual(a: PanelInputs, b: PanelInputs): boolean {
  return stableJson(a) === stableJson(b);
}

/**
 * Что делать автосохранению: `none` — сохранять нечего (нет настроек или они
 * равны последним сохранённым), `wait` — отличаются, но задержка ещё не вышла,
 * `save` — пора писать.
 */
export function nextAutosaveAction(
  prevSaved: CalcInputs | null,
  current: CalcInputs | null,
  elapsedMs: number,
): "none" | "wait" | "save" {
  if (!current) return "none";
  if (calcInputsEqual(prevSaved, current)) return "none";
  return elapsedMs >= AUTOSAVE_DELAY_MS ? "save" : "wait";
}
