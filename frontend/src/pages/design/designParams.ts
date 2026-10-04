// Параметры раскладки, правила зарядов и ВВ правятся в формах страницы, а не
// в документе паспорта. Сервер сравнивает их как проектную часть, поэтому
// формы и паспорт сходятся в двух точках: формы берутся из паспорта после
// каждой загрузки с сервера, а на сервер паспорт уходит только с тем, что в
// его статусе можно править, — замороженные части как хранятся.
import { canEdit, MUTATION_PAYLOAD_KEYS, type MutationKind } from "../../lib/lifecycle";
import { DEFAULT_CHARGE_RULES, DEFAULT_PATTERN_PARAMS, type BlastDesign, type ChargeRules, type PatternParams } from "../../types/design";
import type { DesignState } from "./designReducer";

export type DesignParams = { patternParams: PatternParams; chargeRules: ChargeRules; explosiveKey: string };

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
        pattern_params: params.patternParams as unknown as Record<string, unknown>,
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
