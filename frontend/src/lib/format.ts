export function ruNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toFixed(digits).replace(".", ",");
}

/** Дата ISO («2026-09-01» или с временем) по-русски: «01.09.2026». Время отбрасывается. */
export function ruDate(value: string | null | undefined): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value ?? "");
  return match ? `${match[3]}.${match[2]}.${match[1]}` : "—";
}

/**
 * Момент ISO с часовым поясом («2026-10-02T19:08:10+00:00» — так сервер отдаёт
 * время загрузки) в часовом поясе пользователя: «03.10.2026 00:08».
 */
export function ruDateTime(value: string | null | undefined): string {
  const moment = value ? new Date(value) : null;
  if (!moment || Number.isNaN(moment.getTime())) return "—";
  const two = (part: number) => String(part).padStart(2, "0");
  return (
    `${two(moment.getDate())}.${two(moment.getMonth() + 1)}.${moment.getFullYear()} ` +
    `${two(moment.getHours())}:${two(moment.getMinutes())}`
  );
}
