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
