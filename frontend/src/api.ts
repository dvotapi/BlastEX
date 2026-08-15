import type { BlastVariant, Explosive, Rock, User } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!response.ok) {
    let message = "Не удалось выполнить запрос.";
    try {
      const payload = await response.json();
      message = payload.detail || message;
    } catch {
      // Response has no JSON body.
    }
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  me: () => request<User>("/api/v1/auth/me"),
  login: (email: string, password: string) =>
    request<User>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  logout: () => request<void>("/api/v1/auth/logout", { method: "POST" }),
  rocks: () => request<{ items: Rock[]; default_name: string }>("/api/v1/references/rocks"),
  explosives: () =>
    request<{ items: Explosive[]; default_key: string }>("/api/v1/references/explosives"),
  optimize: (input: {
    rock: Rock;
    explosive: Explosive;
    lumpSize: number;
    benchHeight: number;
    overdrill: number;
    spacing: number;
    threshold: number;
  }) =>
    request<{ variants: BlastVariant[] }>("/api/v1/blast/optimize", {
      method: "POST",
      body: JSON.stringify({
        rock: input.rock,
        explosive: {
          name: input.explosive.name,
          density_t_m3: input.explosive.density_t_m3,
          power_mj_kg: input.explosive.power_mj_kg,
        },
        target: {
          lump_size_mm: input.lumpSize,
          hole_diameter_mm: 0,
          overdrill_m: input.overdrill,
          hole_oversize_coeff: 1.05,
          spacing_coeff_m: input.spacing,
          bench_height_m: input.benchHeight,
        },
        max_oversize_threshold_pct: input.threshold,
      }),
    }),
};
