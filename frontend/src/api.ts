import type { BlastVariant, Explosive, Rock, User } from "./types";
import type {
  AnalyzeResponse,
  BlastDesign,
  BlockContour,
  ChargeExplosive,
  ChargeGenerateResponse,
  ChargeRules,
  CostScenarioId,
  DesignCostResult,
  DesignSummary,
  Hole,
  PatternGenerateResponse,
  PpvRequest,
  SchemeType,
  TieGenerateResponse,
  TieParams,
} from "./types/design";

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
  design: {
    pattern: (contour: BlockContour, params: Record<string, unknown>, existingHoles: Hole[] = []) =>
      request<PatternGenerateResponse>("/api/v1/design/pattern", {
        method: "POST",
        body: JSON.stringify({ contour, params, existing_holes: existingHoles }),
      }),
    charge: (holes: Hole[], rules: ChargeRules, explosive: ChargeExplosive) =>
      request<ChargeGenerateResponse>("/api/v1/design/charge", {
        method: "POST",
        body: JSON.stringify({ holes, rules, explosive }),
      }),
    tie: (holes: Hole[], scheme: SchemeType, params: TieParams) =>
      request<TieGenerateResponse>("/api/v1/design/tie/generate", {
        method: "POST",
        body: JSON.stringify({ holes, scheme, params }),
      }),
    analyze: (design: BlastDesign, isolineStepMs: number, micWindowMs: number, ppv: PpvRequest | null) =>
      request<AnalyzeResponse>("/api/v1/design/analyze", {
        method: "POST",
        body: JSON.stringify({ design, isoline_step_ms: isolineStepMs, mic_window_ms: micWindowMs, ppv }),
      }),
    cost: (design: BlastDesign, scenarioId: CostScenarioId) =>
      request<DesignCostResult>("/api/v1/design/cost", {
        method: "POST",
        body: JSON.stringify({ design, scenario_id: scenarioId }),
      }),
    passportUrl: (designId: string) => `/api/v1/design/plans/${designId}/passport.html`,
    listPlans: () => request<{ items: DesignSummary[] }>("/api/v1/design/plans"),
    createPlan: (design: BlastDesign) =>
      request<BlastDesign>("/api/v1/design/plans", { method: "POST", body: JSON.stringify(design) }),
    getPlan: (designId: string) => request<BlastDesign>(`/api/v1/design/plans/${designId}`),
    savePlan: (designId: string, design: BlastDesign) =>
      request<BlastDesign>(`/api/v1/design/plans/${designId}`, { method: "PUT", body: JSON.stringify(design) }),
    deletePlan: (designId: string) => request<void>(`/api/v1/design/plans/${designId}`, { method: "DELETE" }),
    exportCsv: async (designId: string, fileName: string) => {
      const response = await fetch(`/api/v1/design/plans/${designId}/export.csv`, { credentials: "include" });
      if (!response.ok) throw new Error("Не удалось экспортировать паспорт.");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = fileName;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    },
  },
};
