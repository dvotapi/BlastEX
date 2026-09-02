export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!response.ok) {
    let message = "Не удалось выполнить запрос.";
    try {
      const payload = await response.json();
      if (typeof payload.detail === "string") message = payload.detail;
      else if (payload.detail && typeof payload.detail.message === "string") message = payload.detail.message;
    } catch {
      // Response has no JSON body.
    }
    throw new Error(message);
  }
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
  if (!response.ok) {
    let message = "Не удалось загрузить файл.";
    try {
      const payload = await response.json();
      if (typeof payload.detail === "string") message = payload.detail;
      else if (payload.detail && typeof payload.detail.message === "string") message = payload.detail.message;
    } catch {
      // Response has no JSON body.
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export const get = <T,>(path: string) => request<T>(path);
export const post = <T,>(path: string, body: unknown) =>
  request<T>(path, { method: "POST", body: JSON.stringify(body) });
export const put = <T,>(path: string, body: unknown) =>
  request<T>(path, { method: "PUT", body: JSON.stringify(body) });
export const del = <T,>(path: string) => request<T>(path, { method: "DELETE" });
