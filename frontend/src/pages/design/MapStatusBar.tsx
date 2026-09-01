import { ruNumber } from "../../lib/format";
import type { Vec2 } from "../../lib/geometry2d";

export function MapStatusBar({
  cursorWorld,
  scalePxPerM,
  gridStepM,
  selectedCount,
  issueCount,
  measureDistanceM,
  measureActive,
}: {
  cursorWorld: Vec2 | null;
  scalePxPerM: number;
  gridStepM: number;
  selectedCount: number;
  issueCount: number;
  measureDistanceM: number | null;
  measureActive: boolean;
}) {
  return (
    <div className="map-status-bar" aria-live="polite">
      <span className="map-status-item">
        {cursorWorld
          ? `X ${ruNumber(cursorWorld.x, 1)} · Y ${ruNumber(cursorWorld.y, 1)} м`
          : "Курсор вне карты"}
      </span>
      <span className="map-status-sep">|</span>
      <span className="map-status-item">сетка {ruNumber(gridStepM, gridStepM >= 1 ? 1 : 2)} м</span>
      <span className="map-status-sep">|</span>
      <span className="map-status-item">{ruNumber(scalePxPerM, scalePxPerM >= 10 ? 0 : 2)} px/м</span>
      <span className="map-status-sep">|</span>
      <span className="map-status-item">
        выделено {selectedCount}
      </span>
      <span className="map-status-sep">|</span>
      <span className={`map-status-item${issueCount > 0 ? " has-issues" : ""}`}>
        замечаний {issueCount}
      </span>
      {measureActive && (
        <>
          <span className="map-status-sep">|</span>
          <span className="map-status-item measure">
            {measureDistanceM !== null
              ? `измерение ${ruNumber(measureDistanceM, 2)} м`
              : "измерение: укажите вторую точку"}
          </span>
        </>
      )}
    </div>
  );
}
