import { useMemo, useState } from "react";
import {
  LAYER_LABELS,
  VIEW_PRESET_LABELS,
  applyViewPreset,
  filterLayers,
  type DesignViewState,
  type ExtendedLayerId,
  type ViewPresetId,
} from "./viewPresets";

const PRESET_ORDER: ViewPresetId[] = [
  "survey",
  "pattern",
  "charge",
  "network",
  "timing",
  "actual",
  "review",
];

export function VisibilityPanel({
  view,
  onChange,
}: {
  view: DesignViewState;
  onChange: (next: DesignViewState) => void;
}) {
  const [query, setQuery] = useState("");
  const visibleLayers = useMemo(() => filterLayers(query), [query]);

  function toggleLayer(id: ExtendedLayerId) {
    onChange({
      ...view,
      layers: { ...view.layers, [id]: !view.layers[id] },
    });
  }

  function selectPreset(preset: ViewPresetId) {
    onChange(applyViewPreset(preset, view));
  }

  return (
    <div className="visibility-panel" aria-label="Видимость слоёв">
      <b>Слои карты</b>
      <div className="visibility-presets">
        {PRESET_ORDER.map((preset) => (
          <button
            key={preset}
            type="button"
            className={view.preset === preset ? "active" : ""}
            title={`Предустановка «${VIEW_PRESET_LABELS[preset]}»`}
            onClick={() => selectPreset(preset)}
          >
            {VIEW_PRESET_LABELS[preset]}
          </button>
        ))}
      </div>
      <input
        className="visibility-search"
        type="search"
        placeholder="Поиск слоя…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        aria-label="Поиск слоя"
      />
      <div className="visibility-layer-list">
        {visibleLayers.map((id) => (
          <label key={id}>
            <input
              type="checkbox"
              checked={view.layers[id]}
              onChange={() => toggleLayer(id)}
            />
            <span>{LAYER_LABELS[id]}</span>
          </label>
        ))}
        {visibleLayers.length === 0 && <small className="visibility-empty">Слои не найдены</small>}
      </div>
    </div>
  );
}
