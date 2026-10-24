// Параметры раскладки, правила зарядов и ВВ правятся в формах страницы, а не
// в документе паспорта. Сервер сравнивает их как проектную часть, поэтому
// формы и паспорт сходятся в двух точках: формы берутся из паспорта после
// каждой загрузки с сервера, а на сервер паспорт уходит только с тем, что в
// его статусе можно править, — замороженные части как хранятся.
import { canEdit, MUTATION_PAYLOAD_KEYS, type MutationKind } from "../../lib/lifecycle";
import { DEFAULT_CHARGE_RULES, DEFAULT_PATTERN_PARAMS, type BenchSurface, type BlastDesign, type ChargeRules, type PatternParams, type TieParams } from "../../types/design";
import { clampFaceAngleFromVertical } from "../../lib/faceAngle";
import type { DesignState } from "./designReducer";

export type DesignParams = { patternParams: PatternParams; chargeRules: ChargeRules; explosiveKey: string };

/** Сетка для q в правилах зарядов: шаги a × b раскладки. */
export interface ChargeGrid {
  grid_a_m: number;
  grid_b_m: number;
}

/** Виды сетки со своим шагом b; прочие (нет ключа, «square», неизвестный) — квадрат. */
const OWN_BURDEN_PATTERNS: ReadonlySet<unknown> = new Set(["rectangular", "staggered", "variable", "domain_dependent"]);

/**
 * Сетка для q по параметрам раскладки — как строит генератор (`design/pattern.py`):
 * у квадрата b = a, у остальных `burden_b_m`, без него (пусто или 0) — тоже a.
 */
export function chargeGridOf(params: Pick<PatternParams, "pattern" | "spacing_a_m" | "burden_b_m">): ChargeGrid {
  const own = OWN_BURDEN_PATTERNS.has(params.pattern) && params.burden_b_m > 0;
  const b = own ? params.burden_b_m : params.spacing_a_m;
  return { grid_a_m: params.spacing_a_m, grid_b_m: b };
}

const MUTATION_KINDS: MutationKind[] = ["designed", "execution", "measured", "metadata"];

/** Формы по паспорту: чего в паспорте нет — умолчание (ВВ — умолчание справочника). */
export function paramsFromDesign(design: BlastDesign, defaultExplosiveKey: string): DesignParams {
  return {
    patternParams: { ...DEFAULT_PATTERN_PARAMS, ...(design.pattern_params as Partial<PatternParams>) },
    chargeRules: { ...DEFAULT_CHARGE_RULES, ...(design.charge_rules as Partial<ChargeRules>) },
    explosiveKey: design.explosive_key || defaultExplosiveKey,
  };
}

/**
 * Паспорт для сервера. Что в статусе паспорта править нельзя, уходит как
 * хранится: формы могли разойтись с паспортом (умолчания поверх старого
 * паспорта, вариант из «Расчёта»), правка могла проскочить мимо блокировки
 * интерфейса, и любое такое расхождение сервер отклонил бы целиком.
 */
export function designWithParams(state: Pick<DesignState, "present" | "saved">, params: DesignParams): BlastDesign {
  const status = state.present.lifecycle_status;
  let payload: BlastDesign = canEdit(status, "designed")
    ? {
        ...state.present,
        // ключи со значением undefined (сброшенный наклон рядов) в паспорт не пишем
        pattern_params: Object.fromEntries(Object.entries(params.patternParams).filter(([, v]) => v !== undefined)),
        charge_rules: params.chargeRules as unknown as Record<string, unknown>,
        explosive_key: params.explosiveKey,
      }
    : state.present;
  for (const kind of MUTATION_KINDS) {
    if (canEdit(status, kind)) continue;
    const stored = Object.fromEntries(MUTATION_PAYLOAD_KEYS[kind].map((key) => [key, state.saved[key]]));
    payload = { ...payload, ...stored };
  }
  return payload;
}

/** Одинаковы в JSON: порядок ключей и поля со значением undefined не в счёт. */
function sameJson(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (typeof a !== "object" || typeof b !== "object" || a === null || b === null) return false;
  if (Array.isArray(a) || Array.isArray(b)) {
    if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length) return false;
    return a.every((item, index) => sameJson(item, b[index]));
  }
  const left = a as Record<string, unknown>;
  const right = b as Record<string, unknown>;
  const keys = Object.keys(left).filter((key) => left[key] !== undefined);
  if (keys.length !== Object.keys(right).filter((key) => right[key] !== undefined).length) return false;
  return keys.every((key) => sameJson(left[key], right[key]));
}

/**
 * Есть ли то, что «Сохранить» записало бы в паспорт. Формы сравниваются с
 * тем, что они показали после загрузки: умолчания поверх пустых ключей
 * правкой не считаются; замороженное в статусе паспорта не в счёт вовсе —
 * сохранить его нельзя, и переход из-за него не должен запираться.
 */
export function hasUnsavedChanges(state: Pick<DesignState, "present" | "saved">, params: DesignParams, defaultExplosiveKey: string): boolean {
  const stored = { present: state.saved, saved: state.saved };
  return !sameJson(designWithParams(state, params), designWithParams(stored, paramsFromDesign(state.saved, defaultExplosiveKey)));
}

/**
 * Угол откоса объекта из «Расчёта» (от вертикали, °) → бровка проекта (от
 * горизонтали). Только для нового проекта — без вершин контура; у проекта с
 * контуром угол уже выбран, его не трогаем. Угол обрезается до 0–60° от
 * вертикали: 90° дали бы откос 0° от горизонтали, сервер его не примет.
 */
export function benchPatchFromObjectAngle(
  design: Pick<BlastDesign, "contour">,
  angleFromVerticalDeg: number | null | undefined,
): Partial<BenchSurface> | null {
  if (angleFromVerticalDeg === null || angleFromVerticalDeg === undefined) return null;
  if (!Number.isFinite(angleFromVerticalDeg)) return null;
  if (design.contour.vertices.length > 0) return null;
  return { face_angle_deg: 90 - clampFaceAngleFromVertical(angleFromVerticalDeg) };
}

/**
 * Порода из «Расчёта» при переносе варианта: ставится новому проекту и
 * проекту без породы, выбранную в проекте не перетирает. Пустое имя и
 * проект, проектную часть которого править нельзя, — null.
 */
export function rockNameFromTransfer(
  design: Pick<BlastDesign, "design_id" | "rock_name" | "lifecycle_status">,
  rockName: string | null | undefined,
): string | null {
  const name = (rockName ?? "").trim();
  if (!name) return null;
  if (!canEdit(design.lifecycle_status, "designed")) return null;
  if (design.design_id && design.rock_name.trim()) return null;
  return name === design.rock_name ? null : name;
}

/**
 * Параметры построения коммутации. Вид основной сетки (`main_kind`) нужен
 * схеме «Магистраль + цепочки»: по нему сетка вида «стабилизация» или
 * «сателлит» — столбцы с магистралью, а не вставки. Ряды решётки стеночного
 * вида — столбцы и без него (по номеру ряда).
 */
export function tieRequestParams(tieParams: TieParams, selectedHoleIds: string[], mainKind: string): TieParams {
  return { ...tieParams, selected_hole_ids: selectedHoleIds, main_kind: mainKind };
}
