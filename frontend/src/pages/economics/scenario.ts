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
export function draftFromRun(run: EconomicsRun, name: string): Draft {
  const rawParameters = run.parameters as unknown as ModelParameters;
  // Прогоны, сохранённые до появления полей субподряда бурения, не несут их
  // вовсе — `undefined`, а не `null`. `SubcontractDrillingEditor.tsx`
  // проверяет строго `!== null` (бейдж «Ручной», доступность кнопки
  // сохранения), и `undefined` вёл себя иначе, чем ожидается, вплоть до
  // отправки `rate_rub: undefined` на сервер. `??` подставляет `null` только
  // когда поля нет вовсе (`undefined`) — настоящее значение, включая явный
  // `null`, остаётся как есть.
  const parameters: ModelParameters = {
    ...rawParameters,
    subcontract_rate_code: rawParameters.subcontract_rate_code ?? null,
    subcontract_rate_rub: rawParameters.subcontract_rate_rub ?? null,
    reference_revision_id: "",
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
