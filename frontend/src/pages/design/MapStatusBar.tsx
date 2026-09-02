import { ruNumber } from "../../lib/format";
import type { HealthSummary } from "./holeHealth";
import { HEALTH_LABELS, type HoleHealthCode } from "./holeHealth";

export type MapStatusMeasure = {
  distanceM: number;
  azimuthDeg: number;
  deltaX: number;
  deltaY: number;
  label?: string;
} | null;

export function MapStatusBar({
  cursorX,
  cursorY,
  scalePxPerM,
  selectedCount,
  health,
  measure,
  onIssueClick,
}: {
  cursorX: number | null;
  cursorY: number | null;
  scalePxPerM: number;
  selectedCount: number;
  health: HealthSummary;
  measure: MapStatusMeasure;
  onIssueClick: (holeId: string) => void;
}) {
  const firstIssue = health.issues[0];

  return (
    <div className="map-status-bar" role="status" aria-live="polite">
      <span>
        {cursorX !== null && cursorY !== null
          ? `X ${ruNumber(cursorX, 1)} · Y ${ruNumber(cursorY, 1)} м`
          : "Курсор вне карты"}
      </span>
      <span className="map-status-sep">|</span>
      <span>{ruNumber(scalePxPerM, scalePxPerM >= 10 ? 0 : 2)} px/м</span>
      <span className="map-status-sep">|</span>
      <span>выбрано: {selectedCount}</span>
      {measure && (
        <>
          <span className="map-status-sep">|</span>
          <span>
            {measure.label ? `${measure.label}: ` : ""}
            {ruNumber(measure.distanceM, 2)} м · азимут {ruNumber(measure.azimuthDeg, 1)}° · ΔX {ruNumber(measure.deltaX, 2)} · ΔY {ruNumber(measure.deltaY, 2)}
          </span>
        </>
      )}
      <span className="map-status-sep">|</span>
      {health.issueCount > 0 ? (
        <button
          type="button"
          className="map-status-issues"
          onClick={() => firstIssue && onIssueClick(firstIssue.holeId)}
          title={health.issues.map((i) => `${i.holeId}: ${i.label}`).join("\n")}
        >
          замечаний: {health.issueCount}
        </button>
      ) : (
        <span className="map-status-ok">замечаний: 0</span>
      )}
    </div>
  );
}

export function healthIssueTitle(code: HoleHealthCode): string {
  return HEALTH_LABELS[code];
}
