import type { DataRole, DesignLifecycleStatus, OverlayMetric } from "../types/design";
import { isFragmentationMapMetric, isMovementMapMetric, isSpatialMapMetric } from "../types/design";

export const LIFECYCLE_STATUSES: DesignLifecycleStatus[] = [
  "draft",
  "in_review",
  "approved",
  "executed",
  "closed",
];

export const STATUS_LABELS_RU: Record<DesignLifecycleStatus, string> = {
  draft: "черновик",
  in_review: "на проверке",
  approved: "утверждён",
  executed: "выполнен",
  closed: "закрыт",
};

export const ROLE_CODES: Record<DataRole, "DESIGNED" | "EXECUTED" | "PREDICTED" | "MEASURED"> = {
  designed: "DESIGNED",
  executed: "EXECUTED",
  predicted: "PREDICTED",
  measured: "MEASURED",
};

export const ROLE_LABELS_RU: Record<DataRole, string> = {
  designed: "проект",
  executed: "исполнение",
  predicted: "прогноз",
  measured: "замер",
};

export const TRANSITION_LABELS: Record<string, string> = {
  "draft→in_review": "На проверку",
  "in_review→draft": "Вернуть в черновик",
  "in_review→approved": "Утвердить",
  "approved→executed": "Отметить выполненным",
  "executed→closed": "Закрыть паспорт",
};

export type WorkflowStageId =
  | "survey"
  | "geology"
  | "pattern"
  | "charge"
  | "timing"
  | "simulation"
  | "execution"
  | "intelligence"
  | "scenarios"
  | "report";

export type WorkflowStage = {
  id: WorkflowStageId;
  label: string;
  role: DataRole;
  mutation: "designed" | "execution" | "measured" | "metadata" | "";
};

export const WORKFLOW_STAGES: WorkflowStage[] = [
  { id: "survey", label: "Съёмка", role: "designed", mutation: "designed" },
  { id: "geology", label: "Геология", role: "designed", mutation: "designed" },
  { id: "pattern", label: "Сетка", role: "designed", mutation: "designed" },
  { id: "charge", label: "Заряд", role: "designed", mutation: "designed" },
  { id: "timing", label: "Тайминг", role: "designed", mutation: "designed" },
  { id: "simulation", label: "Симуляция", role: "predicted", mutation: "" },
  { id: "execution", label: "Исполнение", role: "executed", mutation: "execution" },
  { id: "intelligence", label: "Интеллект", role: "predicted", mutation: "" },
  { id: "scenarios", label: "Сценарии", role: "predicted", mutation: "" },
  { id: "report", label: "Отчёт", role: "designed", mutation: "metadata" },
];

const ALLOWED_MUTATIONS: Record<DesignLifecycleStatus, ReadonlySet<string>> = {
  draft: new Set(["designed", "execution", "measured", "metadata"]),
  in_review: new Set(["metadata"]),
  approved: new Set(["execution", "measured", "metadata"]),
  executed: new Set(["execution", "measured", "metadata"]),
  closed: new Set(),
};

const ALLOWED_TRANSITIONS: Record<DesignLifecycleStatus, DesignLifecycleStatus[]> = {
  draft: ["in_review"],
  in_review: ["draft", "approved"],
  approved: ["executed"],
  executed: ["closed"],
  closed: [],
};

export function normalizeLifecycleStatus(value: string | undefined | null): DesignLifecycleStatus {
  const text = String(value || "draft").trim().toLowerCase().replace("-", "_");
  if ((LIFECYCLE_STATUSES as string[]).includes(text)) return text as DesignLifecycleStatus;
  return "draft";
}

export function statusLabel(status: string | undefined | null): string {
  return STATUS_LABELS_RU[normalizeLifecycleStatus(status)];
}

export function transitionLabel(fromStatus: string, toStatus: string): string {
  return TRANSITION_LABELS[`${normalizeLifecycleStatus(fromStatus)}→${normalizeLifecycleStatus(toStatus)}`]
    || `Перевести в «${statusLabel(toStatus)}»`;
}

export function allowedTransitions(status: string | undefined | null): DesignLifecycleStatus[] {
  return ALLOWED_TRANSITIONS[normalizeLifecycleStatus(status)];
}

export function canEditDesigned(status: string | undefined | null): boolean {
  return ALLOWED_MUTATIONS[normalizeLifecycleStatus(status)].has("designed");
}

export function canEditExecution(status: string | undefined | null): boolean {
  return ALLOWED_MUTATIONS[normalizeLifecycleStatus(status)].has("execution");
}

export function canEditMeasured(status: string | undefined | null): boolean {
  return ALLOWED_MUTATIONS[normalizeLifecycleStatus(status)].has("measured");
}

export function canEditMetadata(status: string | undefined | null): boolean {
  return ALLOWED_MUTATIONS[normalizeLifecycleStatus(status)].has("metadata");
}

export function canDeletePlan(status: string | undefined | null): boolean {
  const current = normalizeLifecycleStatus(status);
  return current === "draft" || current === "in_review";
}

export function isRecordFrozen(status: string | undefined | null): boolean {
  return normalizeLifecycleStatus(status) === "closed";
}

export function freezeMessage(status: string | undefined | null, mutation: "designed" | "execution" | "measured" = "designed"): string {
  const current = normalizeLifecycleStatus(status);
  const label = STATUS_LABELS_RU[current];
  if (current === "closed") {
    return "Паспорт закрыт: проект, исполнение и замер заморожены. Создайте ревизию, чтобы продолжить работу.";
  }
  if (mutation === "designed") {
    return `Паспорт в статусе «${label}»: слой DESIGNED заморожен. Сетку, заряд и тайминг нельзя править.`;
  }
  if (mutation === "execution") {
    return `Паспорт в статусе «${label}»: слой EXECUTED сейчас нельзя менять.`;
  }
  return `Паспорт в статусе «${label}»: слой MEASURED сейчас нельзя менять.`;
}

export function overlayRole(metric: OverlayMetric | ""): DataRole {
  if (!metric) return "designed";
  if (isFragmentationMapMetric(metric) || isSpatialMapMetric(metric) || isMovementMapMetric(metric)) {
    return "predicted";
  }
  return "designed";
}

export function formatRoleChip(role: DataRole): string {
  return `${ROLE_LABELS_RU[role]} / ${ROLE_CODES[role]}`;
}
