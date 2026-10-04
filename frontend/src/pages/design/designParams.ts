// Параметры раскладки, правила зарядов и ВВ правятся в формах страницы, а не
// в документе паспорта. Сервер сравнивает их как проектную часть, поэтому
// формы и паспорт сходятся в двух точках: формы берутся из паспорта после
// каждой загрузки с сервера, а паспорт уходит на сервер с формами только пока
// проектная часть открыта для правки.
import { DEFAULT_CHARGE_RULES, DEFAULT_PATTERN_PARAMS, type BlastDesign, type ChargeRules, type PatternParams } from "../../types/design";
import type { DesignState } from "./designReducer";

export type DesignParams = { patternParams: PatternParams; chargeRules: ChargeRules; explosiveKey: string };

/** Формы по паспорту: чего в паспорте нет — умолчание; без ВВ в паспорте остаётся выбранное. */
export function paramsFromDesign(design: BlastDesign, currentExplosiveKey: string): DesignParams {
  return {
    patternParams: { ...DEFAULT_PATTERN_PARAMS, ...(design.pattern_params as Partial<PatternParams>) },
    chargeRules: { ...DEFAULT_CHARGE_RULES, ...(design.charge_rules as Partial<ChargeRules>) },
    explosiveKey: design.explosive_key || currentExplosiveKey,
  };
}

/**
 * Паспорт для сервера. С замороженной проектной частью — как хранится:
 * формы могли разойтись с ним (умолчания поверх старого паспорта, вариант из
 * «Расчёта»), и любое расхождение сервер отклонит как правку проекта.
 */
export function designWithParams(document: BlastDesign, params: DesignParams, locked: boolean): BlastDesign {
  if (locked) return document;
  return {
    ...document,
    pattern_params: params.patternParams as unknown as Record<string, unknown>,
    charge_rules: params.chargeRules as unknown as Record<string, unknown>,
    explosive_key: params.explosiveKey,
  };
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
 * Есть ли то, чего нет в паспорте на сервере. Формы сравниваются с тем, что
 * они показали после загрузки, — умолчания поверх пустых ключей правкой не
 * считаются; у замороженной проектной части формы не в счёт вовсе.
 */
export function hasUnsavedChanges(state: Pick<DesignState, "present" | "saved">, params: DesignParams, locked: boolean): boolean {
  const loaded = paramsFromDesign(state.saved, params.explosiveKey);
  return !sameJson(designWithParams(state.present, params, locked), designWithParams(state.saved, loaded, locked));
}
