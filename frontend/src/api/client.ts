/**
 * Русские тексты ошибок проверки из `details[].msg` (ответ 422), без повторов.
 * Свои валидаторы API пишут по-русски и точнее общего `detail`; стандартные
 * тексты pydantic — английские, их пользователю не показываем. У валидаторов
 * на `ValueError` (например, `api/schemas/economics.py`) pydantic сам
 * приписывает перед текстом «Value error, » — убираем его до проверки на
 * кириллицу, иначе он остаётся в сообщении пользователю.
 */
function validationMessages(details: unknown): string[] {
  if (!Array.isArray(details)) return [];
  const messages = details
    .map((item) => (typeof item === "object" && item !== null && typeof item.msg === "string" ? item.msg : ""))
    .map((message) => message.replace(/^Value error, /, ""))
    .filter((message) => /[А-Яа-яЁё]/.test(message));
  return [...new Set(messages)];
}

/** Текст ошибки из ответа: FastAPI кладёт его в `detail` строкой или объектом с
 * `message`; при 422 — ещё русские тексты валидаторов из `details`. */
export async function errorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const payload = await response.json();
    if (typeof payload.detail === "string") {
      const messages = validationMessages(payload.details);
      return messages.length ? `${payload.detail.replace(/\.$/, "")}: ${messages.join(" ")}` : payload.detail;
    }
    if (payload.detail && typeof payload.detail.message === "string") return payload.detail.message;
  } catch {
    // В ответе нет тела JSON.
  }
  return fallback;
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!response.ok) throw new Error(await errorMessage(response, "Не удалось выполнить запрос."));
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function requestSvg(path: string, init?: RequestInit): Promise<string> {
  const response = await fetch(path, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!response.ok) throw new Error("Не удалось построить схему заряда.");
  return response.text();
}

/** Загрузка файла. Content-Type не задаём: с FormData его ставит браузер вместе с boundary. */
export async function postFile<T>(path: string, file: File, field = "file"): Promise<T> {
  const form = new FormData();
  form.append(field, file);
  const response = await fetch(path, { method: "POST", credentials: "include", body: form });
  if (!response.ok) throw new Error(await errorMessage(response, "Не удалось загрузить файл."));
  return response.json() as Promise<T>;
}

export const get = <T,>(path: string) => request<T>(path);
export const post = <T,>(path: string, body: unknown) =>
  request<T>(path, { method: "POST", body: JSON.stringify(body) });
export const put = <T,>(path: string, body: unknown) =>
  request<T>(path, { method: "PUT", body: JSON.stringify(body) });
export const del = <T,>(path: string) => request<T>(path, { method: "DELETE" });
