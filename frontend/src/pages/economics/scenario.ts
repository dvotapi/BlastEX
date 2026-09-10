/**
 * Состояние черновика сценария вкладки «Экономика».
 *
 * «Сценарий» в шапке — это либо ещё не сохранённый черновик, либо открытый
 * сохранённый прогон. Черновик расширяет `Variant` (тот же тип, что и
 * столбцы сметы в `variants.ts`) двумя полями: откуда он открыт и с каким
 * состоянием параметров он был в последний раз сохранён — по ним `isDirty`
 * узнаёт, разошёлся ли черновик с прогоном, не спрашивая бэкенд.
 */
import type { EconomicsRun, EconomicsRunSummary, ModelParameters } from "../../types/blockEconomics";
import { makeVariant, type Variant } from "./variants";

export type Draft = Variant & {
  /** Прогон, из которого открыт черновик; null — черновик с умолчаний, ещё не сохранялся. */
  sourceRunId: string | null;
  /** Снимок параметров на момент последнего сохранения — `JSON.stringify`, сравнивается в `isDirty`. */
  savedKey: string;
};

function paramsKey(parameters: ModelParameters): string {
  return JSON.stringify(parameters);
}

/**
 * Значение поля параметров из прогона, из каталога умолчаний или из пустого
 * значения — в этом порядке.
 *
 * Отсутствие поля (`undefined`) и явная пустота (`null`) — разные вещи:
 * `rig_plan_shifts: null` в прогоне означает «считать по нормативу», и
 * подменять его умолчанием нельзя. Поэтому проверка именно на `undefined`, а
 * не оператор `??`, который склеил бы оба случая.
 */
function pick<K extends keyof ModelParameters>(
  raw: Partial<ModelParameters>,
  base: ModelParameters | null,
  key: K,
  empty: ModelParameters[K],
): ModelParameters[K] {
  if (raw[key] !== undefined) return raw[key] as ModelParameters[K];
  if (base && base[key] !== undefined) return base[key];
  return empty;
}

/**
 * Новый черновик с параметров по умолчанию (`ModelDefaults.parameters`) —
 * ещё ничего не сохранено, поэтому `savedKey` заведомо не совпадает ни с
 * одним снимком параметров: такой черновик всегда «грязный».
 */
export function draftFromDefaults(name: string, parameters: ModelParameters): Draft {
  return { ...makeVariant(name, parameters), sourceRunId: null, savedKey: "" };
}

/**
 * Черновик, открытый из сохранённого прогона: параметры и `savedKey`
 * совпадают, поэтому `isDirty` возвращает `false`, пока их не тронули.
 *
 * `run.parameters` типизирован как `Record<string, unknown>`, потому что
 * бэкенд кладёт туда результат `ModelParametersSchema.to_dict()` — TS-тип
 * `EconomicsRun` не знает об этой схеме. Приведение безопасно: маршрут,
 * который отдаёт `EconomicsRun`, всегда пишет в это поле именно
 * сериализованные параметры модели.
 *
 * Открытый из прогона черновик — это НОВЫЙ редактируемый артефакт для
 * дальнейшей работы, а не точная историческая копия: `reference_revision_id`
 * из прогона (зафиксированный на момент его сохранения) намеренно
 * отбрасывается и заменяется на `""` — тот же приём, что уже используют
 * черновики по умолчанию из `model-defaults`, означающий «считать на
 * актуальной ревизии». Иначе открытые для правки редакторы (комбобоксы
 * номенклатуры/техники/должностей) показывали бы опции из ТЕКУЩЕГО каталога
 * (`defaults`), а пересчёт шёл бы по ИСТОРИЧЕСКОЙ ревизии, пришпиленной в
 * прогоне, — несостыковка цен и списка опций, вплоть до отсутствия в
 * текущем каталоге позиции, выбранной в прошлой ревизии. Сам прогон в
 * `economics_runs` при этом не меняется и остаётся историческим снимком со
 * своей исходной ревизией — это решение касается только нового черновика.
 */
export function draftFromRun(
  run: EconomicsRun,
  name: string,
  /** Параметры по умолчанию текущего каталога; null — каталог ещё не загружен. */
  fallback: ModelParameters | null = null,
): Draft {
  const raw = run.parameters as unknown as Partial<ModelParameters>;
  // Прогон несёт ровно те поля, которые существовали в схеме на момент его
  // сохранения: у старых прогонов нет ни `services`, ни `machine_plan_shifts`,
  // ни техники эмульсии, ни полей субподряда. Раньше их отсутствие уезжало в
  // черновик как `undefined` и роняло всю страницу на первом же `.length`.
  // Каждое поле названо здесь явно, поэтому новое поле `ModelParameters` не
  // проскочит мимо: TypeScript потребует дописать его в этот объект.
  const parameters: ModelParameters = {
    package_code: pick(raw, fallback, "package_code", ""),
    site_code: pick(raw, fallback, "site_code", ""),
    // Считать на актуальной ревизии, а не на исторической — см. описание выше.
    reference_revision_id: "",
    unit_plan_volume_m3: pick(raw, fallback, "unit_plan_volume_m3", "0"),
    rig_code: pick(raw, fallback, "rig_code", null),
    rig_plan_shifts: pick(raw, fallback, "rig_plan_shifts", null),
    szm_code: pick(raw, fallback, "szm_code", null),
    delivery_truck_code: pick(raw, fallback, "delivery_truck_code", null),
    emulsion_truck_code: pick(raw, fallback, "emulsion_truck_code", null),
    machine_plan_shifts: pick(raw, fallback, "machine_plan_shifts", {}),
    crew: pick(raw, fallback, "crew", []),
    services: pick(raw, fallback, "services", []),
    drilling_executor: pick(raw, fallback, "drilling_executor", "OWN"),
    // Выбор подрядчика — часть самого прогона: его отсутствие означает «не
    // выбран», а не «взять из умолчаний», поэтому каталог здесь не спрашиваем.
    subcontract_rate_code: raw.subcontract_rate_code ?? null,
    subcontract_rate_rub: raw.subcontract_rate_rub ?? null,
    nomenclature: pick(raw, fallback, "nomenclature", {}),
    electric_detonators_qty: pick(raw, fallback, "electric_detonators_qty", "0"),
    overhead_rate: pick(raw, fallback, "overhead_rate", null),
    target_margin_rate: pick(raw, fallback, "target_margin_rate", null),
    vat_rate: pick(raw, fallback, "vat_rate", null),
  };
  return { ...makeVariant(name, parameters), sourceRunId: run.id, savedKey: paramsKey(parameters) };
}

/** Параметры черновика разошлись с последним сохранённым снимком. */
export function isDirty(draft: Draft): boolean {
  return paramsKey(draft.parameters) !== draft.savedKey;
}

/** После сохранения прогона черновик привязывается к нему и перестаёт быть «грязным». */
export function markSaved(draft: Draft, runId: string): Draft {
  return { ...draft, sourceRunId: runId, savedKey: paramsKey(draft.parameters) };
}

/**
 * Пометить черновик сохранённым, только если параметры не изменились с
 * момента, когда прогон был отправлен на сервер — иначе правка, сделанная
 * во время сохранения, тихо считалась бы уже сохранённой, хотя в прогоне
 * лежит более старый снимок. Прогон при этом всё равно привязывается
 * (`sourceRunId`) — он реально создан и существует, просто черновик
 * остаётся «грязным» относительно него.
 */
export function markSavedIfCurrent(draft: Draft, runId: string, submittedParameters: ModelParameters): Draft {
  const submittedKey = paramsKey(submittedParameters);
  if (paramsKey(draft.parameters) !== submittedKey) {
    return { ...draft, sourceRunId: runId };
  }
  return { ...draft, sourceRunId: runId, savedKey: submittedKey };
}

/**
 * Подпись сценария для селектора: имя сохранённого прогона (если черновик
 * открыт из существующего и найден в списке прогонов паспорта) либо имя
 * самого черновика, с пометкой «· черновик», пока параметры не сохранены.
 */
export function scenarioLabel(draft: Draft, runs: EconomicsRunSummary[]): string {
  const savedRun = draft.sourceRunId ? runs.find((run) => run.id === draft.sourceRunId) : undefined;
  const name = savedRun?.name ?? draft.name;
  return isDirty(draft) ? `${name} · черновик` : name;
}
