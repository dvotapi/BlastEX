/** Чистая логика гонки запросов при смене объекта работ в `useWorkspace`.
 * Каждый вызов `setActiveWorkObjectName` получает свой порядковый номер;
 * применять к состоянию можно только ответ последнего запроса — более
 * ранний ответ, пришедший позже, должен быть проигнорирован. */

/** true — ответ (успех или ошибка) относится к последнему запросу и его
 * можно применить к состоянию; false — запрос устарел, ответ отбрасывается. */
export function isLatestObjectRequest(requestId: number, latestRequestId: number): boolean {
  return requestId === latestRequestId;
}

/** Откатывать оптимистично выставленное имя объекта при ошибке нужно,
 * только если запрос всё ещё последний и было что откатывать
 * (у состояния уже было предыдущее имя на момент запроса). */
export function shouldRollbackOnError(
  requestId: number,
  latestRequestId: number,
  previousName: string | undefined
): previousName is string {
  return isLatestObjectRequest(requestId, latestRequestId) && previousName !== undefined;
}

/**
 * Что применить к состоянию из ответа `PUT /workspace/active-object`.
 *
 * Ответ возвращает всё рабочее пространство целиком, но снимок сценария в нём —
 * сохранённый на сервере. Если применить его как есть, несохранённые правки
 * «Бурения» (`drilling_calculator_input`) и «ФОТ» (`labor_*`) молча пропадут
 * при смене объекта. Поэтому снимок остаётся локальным, а из ответа берём
 * только то, что смена объекта действительно меняет: настройки, справочники,
 * предупреждения и цену бурения.
 */
export function mergeWorkspaceAfterObjectSwitch<
  T extends {
    settings: unknown;
    snapshot: unknown;
    references: unknown;
    drilling_price_per_m: number;
    warnings: string[];
  },
>(prev: T, next: T): T {
  return { ...next, snapshot: prev.snapshot };
}
