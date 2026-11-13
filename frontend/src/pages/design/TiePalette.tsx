// Палитра правки коммутации над планом (TASK-017, PR 4): инструменты,
// номиналы ступеней системы (активный — для новых связей и «Ступени») и
// замедление в скважине. Номиналы — из каталога сервера.
import { useEffect, useState } from "react";
import { ruNumber } from "../../lib/format";
import type { TieSystemCatalog } from "../../types/design";
import { stepColor, TIE_TOOLS, type TieTool } from "./tieSteps";

export function TiePalette({
  catalog,
  tool,
  onToolChange,
  activeMs,
  onActiveMsChange,
  downholeMs,
  onDownholeMsChange,
}: {
  catalog: TieSystemCatalog | null;
  tool: TieTool | null;
  onToolChange: (tool: TieTool) => void;
  activeMs: number;
  onActiveMsChange: (ms: number) => void;
  downholeMs: number;
  onDownholeMsChange: (ms: number) => void;
}) {
  const nominals = catalog?.surface_ms ?? [];
  const downhole = catalog?.downhole_ms ?? [];
  const custom = Boolean(catalog?.custom_surface);
  const offNominal = !nominals.includes(activeMs);
  // Текст поля «своё, мс» — свой: набор «170» проходит через номинал 17, и
  // поле, привязанное к активной ступени, очистилось бы посреди ввода.
  const [draft, setDraft] = useState(offNominal ? String(activeMs) : "");
  useEffect(() => {
    setDraft((current) => (Number(current) === activeMs ? current : offNominal ? String(activeMs) : ""));
  }, [activeMs, offNominal]);
  return (
    <div className="tie-palette" role="toolbar" aria-label="Правка коммутации">
      <div className="plan-tool-group">
        {TIE_TOOLS.map((item) => (
          <button
            key={item.id}
            type="button"
            className={tool === item.id ? "active" : ""}
            aria-pressed={tool === item.id}
            title={item.title}
            onClick={() => onToolChange(item.id)}
          >
            {item.label} <kbd>{item.key}</kbd>
          </button>
        ))}
      </div>
      <div className="plan-tool-group tie-steps" role="group" aria-label="Ступень, мс">
        {nominals.map((ms, index) => (
          <button
            key={ms}
            type="button"
            className={`tie-step${activeMs === ms ? " active" : ""}`}
            style={{ borderColor: stepColor(ms, nominals), color: stepColor(ms, nominals) }}
            aria-pressed={activeMs === ms}
            title={`Ступень ${ruNumber(ms, 0)} мс (${index + 1})`}
            onClick={() => onActiveMsChange(ms)}
          >
            {ruNumber(ms, 0)}
          </button>
        ))}
        {custom && (
          <label className={`plan-toggle tie-step-custom${offNominal ? " active" : ""}`}>
            своё, мс
            <input
              type="number"
              min="1"
              step="1"
              aria-label="Своя ступень, мс"
              value={draft}
              placeholder="—"
              onChange={(e) => {
                setDraft(e.target.value);
                const value = Number(e.target.value);
                if (e.target.value !== "" && Number.isFinite(value) && value > 0) onActiveMsChange(value);
              }}
            />
          </label>
        )}
        {!catalog && <small>Номиналы загружаются…</small>}
      </div>
      <div className="plan-tool-group" role="group" aria-label="Замедление в скважине">
        <label className="plan-toggle" title="Замедление внутрискважинного детонатора для инструмента «В скважине»">
          В скважине, мс
          {downhole.length ? (
            <select aria-label="Замедление в скважине, мс" value={downholeMs} onChange={(e) => onDownholeMsChange(Number(e.target.value))}>
              {(downhole.includes(downholeMs) ? downhole : [...downhole, downholeMs].sort((a, b) => a - b)).map((ms) => (
                <option key={ms} value={ms}>{ruNumber(ms, 0)}</option>
              ))}
            </select>
          ) : (
            <input
              type="number"
              min="0"
              step="1"
              aria-label="Замедление в скважине, мс"
              value={downholeMs}
              onChange={(e) => {
                const value = Number(e.target.value);
                if (Number.isFinite(value) && value >= 0) onDownholeMsChange(value);
              }}
            />
          )}
        </label>
      </div>
    </div>
  );
}
