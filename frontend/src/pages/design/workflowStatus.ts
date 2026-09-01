import {
  canEditDesigned,
  canEditExecution,
  canEditMeasured,
  canEditMetadata,
  WORKFLOW_STAGES,
  type WorkflowStageId,
} from "../../lib/lifecycle";
import { networkTies, type BlastDesign, type CoordinateSystem, type SurfaceSet } from "../../types/design";

export type StageStatus = "empty" | "ready" | "error" | "locked";

export const STAGE_ICONS: Record<WorkflowStageId, string> = {
  survey: "⌖",
  geology: "▣",
  pattern: "∷",
  charge: "◎",
  timing: "⏱",
  simulation: "≈",
  execution: "✓",
  intelligence: "λ",
  scenarios: "⊞",
  report: "☰",
};

export function hasSurveyGeometry(document: BlastDesign): boolean {
  return document.contour.vertices.length >= 3
    || Boolean(document.surfaces.top)
    || Boolean(document.surfaces.floor)
    || Boolean(document.surfaces.face);
}

export function isCrsUnconfirmed(cs: CoordinateSystem, hasGeometry: boolean): boolean {
  if (!hasGeometry) return false;
  if (cs.confirmed) return false;
  const unnamed = !cs.name.trim() || cs.name.trim().toLowerCase() === "local";
  return unnamed || cs.epsg == null;
}

export function holeSourceLabel(document: BlastDesign): string {
  const holes = document.holes;
  if (!holes.length) return "нет данных";
  const generated = holes.filter((h) => h.source === "generated").length;
  const manual = holes.filter((h) => h.source === "manual").length;
  if (generated && manual) return "смешанное";
  if (generated) return "по сетке";
  if (manual) return "проектное";
  return "проектное";
}

export function volumeSourceLabel(surfaces: SurfaceSet, hasContour: boolean): string {
  const imported = [surfaces.top, surfaces.floor, surfaces.face].some(
    (item) => item && (item.source_format === "dxf" || /dxf/i.test(item.source_name || "")),
  );
  if (imported) return "из DXF";
  if (hasContour) return "проектное";
  return "нет данных";
}

export function stageStatus(
  stage: WorkflowStageId,
  document: BlastDesign,
  extras: { crsUnconfirmed: boolean },
): StageStatus {
  const spec = WORKFLOW_STAGES.find((item) => item.id === stage);
  const mutation = spec?.mutation ?? "";
  const locked = (
    (mutation === "designed" && !canEditDesigned(document.lifecycle_status))
    || (mutation === "execution" && !canEditExecution(document.lifecycle_status))
    || (mutation === "measured" && !canEditMeasured(document.lifecycle_status))
    || (mutation === "metadata" && !canEditMetadata(document.lifecycle_status))
  );
  if (locked && mutation) return "locked";

  if (stage === "survey" && extras.crsUnconfirmed) return "error";

  const ready = (() => {
    switch (stage) {
      case "survey":
        return hasSurveyGeometry(document);
      case "geology":
        return document.domains.length > 0;
      case "pattern":
        return document.holes.length > 0;
      case "charge":
        return document.loads.length > 0;
      case "timing":
        return networkTies(document.network).length > 0
          || (document.network.starter_items?.length ?? 0) > 0
          || (document.network.starters?.length ?? 0) > 0;
      case "simulation":
        return Boolean(document.blast_result);
      case "execution":
        return document.as_drilled_holes.length > 0
          || document.as_charged_holes.length > 0
          || document.as_fired_holes.length > 0;
      case "intelligence":
        return false;
      case "scenarios":
        return false;
      case "report":
        return Boolean(document.design_id);
      default:
        return false;
    }
  })();
  return ready ? "ready" : "empty";
}

export function statusesForDocument(
  document: BlastDesign,
  extras: { crsUnconfirmed: boolean },
): Record<WorkflowStageId, StageStatus> {
  return Object.fromEntries(
    WORKFLOW_STAGES.map((item) => [item.id, stageStatus(item.id, document, extras)]),
  ) as Record<WorkflowStageId, StageStatus>;
}
