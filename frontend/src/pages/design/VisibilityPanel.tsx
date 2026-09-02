import { useMemo, useState } from "react";
import {
  COLOR_MODE_LABELS,
  LABEL_FIELD_LABELS,
  VIEW_PRESET_LABELS,
  layerGroups,
  type DesignViewState,
  type LayerId,
  type ViewPresetId,
} from "./viewPresets";

const PRESET_ORDER: ViewPresetId[] = ["survey", "pattern", "charge", "network", "timing", "actual", "review"];

export function VisibilityPanel({
  viewState,
  onPresetChange,
  onLayerChange,
  onResetLayers,
  collapsed,
  onToggleCollapsed,
}: {
  viewState: DesignViewState;
  onPresetChange: (preset: ViewPresetId) => void;
  onLayerChange: (id: LayerId, visible: boolean) => void;
  onResetLayers: () => void;
  collapsed: boolean;
  onToggleCollapsed: () => void;
}) {
  const [query, setQuery] = useState("");
  const groups = useMemo(() => layerGroups(query), [query]);

  if (collapsed) {
    return (
      <button type="button" className="visibility-panel-toggle" onClick={onToggleCollapsed} title="Слои и пресеты">
        ☰ Слои
      </button>
    );
  }

  return (
    <div className="visibility-panel" aria-label="Пресеты и слои карты">
      <header>
        <b>Вид</b>
        <button type="button" className="visibility-panel-close" onClick={onToggleCollapsed} aria-label="Свернуть">−</button>
      </header>

      <div className="visibility-presets" role="group" aria-label="Пресеты вида">
        {PRESET_ORDER.map((preset) => (
          <button
            key={preset}
            type="button"
            className={viewState.preset === preset ? "active" : ""}
            onClick={() => onPresetChange(preset)}
            title={`${VIEW_PRESET_LABELS[preset]} · ${LABEL_FIELD_LABELS[viewState.labelField]} · ${COLOR_MODE_LABELS[viewState.colorMode]}`}
          >
            {VIEW_PRESET_LABELS[preset]}
          </button>
        ))}
      </div>

      <div className="visibility-search">
        <input
          type="search"
          placeholder="Поиск слоя…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Поиск слоя"
        />
      </div>

      <div className="visibility-layers">
        {groups.map((group) => (
          <section key={group.group}>
            <small>{group.label}</small>
            {group.items.map((item) => (
              <label key={item.id}>
                <input
                  type="checkbox"
                  checked={viewState.layers[item.id]}
                  onChange={(e) => onLayerChange(item.id, e.target.checked)}
                />
                <i className={`legend-swatch ${item.swatch}`} aria-hidden="true" />
                <span>{item.label}</span>
              </label>
            ))}
          </section>
        ))}
      </div>

      <footer>
        <button type="button" className="secondary-button" onClick={onResetLayers}>Сбросить к пресету</button>
      </footer>
    </div>
  );
}
