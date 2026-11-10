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

/** Ошибка ответа API с HTTP-статусом: «нет такого» (404) отличается от сбоя сервера. */
export class HttpError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "HttpError";
  }
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!response.ok) throw new HttpError(await errorMessage(response, "Не удалось выполнить запрос."), response.status);
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

/** Отправка формы (несколько файлов и поля) — как `postFile`, но форму собирает вызывающий. */
export async function postForm<T>(path: string, form: FormData): Promise<T> {
  const response = await fetch(path, { method: "POST", credentials: "include", body: form });
  if (!response.ok) throw new Error(await errorMessage(response, "Не удалось загрузить файл."));
  return response.json() as Promise<T>;
}

export const get = <T,>(path: string) => request<T>(path);
export const post = <T,>(path: string, body: unknown) =>
  request<T>(path, { method: "POST", body: JSON.stringify(body) });
export const put = <T,>(path: string, body: unknown) =>
  request<T>(path, { method: "PUT", body: JSON.stringify(body) });
export const patch = <T,>(path: string, body: unknown) =>
  request<T>(path, { method: "PATCH", body: JSON.stringify(body) });
export const del = <T,>(path: string) => request<T>(path, { method: "DELETE" });

/** Имя файла из Content-Disposition: `filename*=UTF-8''…`, иначе `filename="…"`. */
function dispositionName(disposition: string): string | null {
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(disposition);
  if (encoded) {
    try {
      return decodeURIComponent(encoded[1].trim());
    } catch {
      // Битое кодирование — берём простое имя.
    }
  }
  return /filename="([^"]+)"/i.exec(disposition)?.[1] ?? null;
}

/** Файл ответа как Blob; ошибка — `HttpError` с русским текстом сервера, а не тело ответа. */
export async function fetchBlob(path: string): Promise<Blob> {
  const response = await fetch(path, { credentials: "include" });
  if (!response.ok) throw new HttpError(await errorMessage(response, "Не удалось получить файл."), response.status);
  return response.blob();
}

/**
 * Скачать файл: имя — из ответа сервера, предупреждение — заголовок
 * `X-BlastEX-Warning` (percent-encoding, например «DWG пока не формируется»).
 */
export async function downloadFile(
  path: string,
  fallbackName: string,
): Promise<{ filename: string; warning: string | null }> {
  const response = await fetch(path, { credentials: "include" });
  if (!response.ok) throw new HttpError(await errorMessage(response, "Не удалось скачать файл."), response.status);
  const filename = dispositionName(response.headers.get("content-disposition") ?? "") ?? fallbackName;
  const header = response.headers.get("x-blastex-warning");
  let warning: string | null = null;
  if (header) {
    try {
      warning = decodeURIComponent(header);
    } catch {
      warning = header;
    }
  }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  return { filename, warning };
}
