import { useMemo, useState } from "react";
import type { SituationPanelSeries } from "./situationLayer";
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

/** Ситуация объекта в «Виде» (TASK-013, PR 4): флажки слоёв — только вид, не паспорт. */
export type SituationPanelModel = {
  series: SituationPanelSeries[];
  hidden: Set<string>;
  /** Сколько версий из ссылки паспорта удалено. */
  missing: number;
  error: string;
  /** Каталог отдал не все версии: у длинных серий — последние. */
  truncated: boolean;
};

function SituationGroup({
  model,
  query,
  onVersion,
  onLayer,
}: {
  model: SituationPanelModel;
  query: string;
  onVersion: (seriesKey: string, sourceId: string) => void;
  onLayer: (key: string, visible: boolean) => void;
}) {
  if (!model.series.length && !model.missing && !model.error) return null;
  const needle = query.trim().toLowerCase();
  const matches = (text: string) => !needle || text.toLowerCase().includes(needle);
  return (
    <section className="visibility-situation" role="group" aria-label="Ситуация">
      <small>Ситуация</small>
      {model.error && <p className="visibility-note">{model.error}</p>}
      {model.missing > 0 && (
        <p className="visibility-note">Удалено версий, на которые ссылается паспорт: {model.missing}</p>
      )}
      {model.truncated && (
        <p className="visibility-note">У длинных серий показаны последние версии (не больше 12).</p>
      )}
      {model.series.map((series) => {
        const passport = series.versions.find((item) => item.sourceId === series.passportId);
        const layers = (series.layers ?? []).filter(
          (layer) => matches(layer.name) || matches(layer.kindLabel) || matches(series.title),
        );
        if (needle && series.layers && !layers.length) return null;
        return (
          <div key={series.key} className="situation-series">
            <div className="situation-series-head">
              <b title={series.title}>{series.title}</b>
              {series.versions.length > 1 ? (
                <select
                  aria-label={`Версия «${series.title}»`}
                  value={series.displayedId}
                  onChange={(event) => onVersion(series.key, event.target.value)}
                >
                  {series.versions.map((item) => (
                    <option key={item.sourceId} value={item.sourceId}>
                      {item.label}
                    </option>
                  ))}
                </select>
              ) : (
                <span>{series.versions[0]?.label}</span>
              )}
            </div>
            {passport && series.passportId !== series.displayedId && (
              <small className="situation-passport">паспорт: {passport.label}</small>
            )}
            {series.layers === null ? (
              <small className="situation-loading">Загружаю…</small>
            ) : (
              layers.map((layer) => (
                <label key={layer.key} title={layer.omitted ? "Слой не уместился в предел ответа" : undefined}>
                  <input
                    type="checkbox"
                    checked={!model.hidden.has(layer.key) && !layer.omitted}
                    disabled={layer.omitted}
                    onChange={(event) => onLayer(layer.key, event.target.checked)}
                  />
                  <i className="legend-swatch situation-swatch" style={{ background: layer.color }} aria-hidden="true" />
                  <span>{layer.name}</span>
                  <em>
                    {layer.kindLabel}
                    {layer.omitted ? " · не уместился" : ""}
                  </em>
                </label>
              ))
            )}
          </div>
        );
      })}
    </section>
  );
}

export function VisibilityPanel({
  viewState,
  onPresetChange,
  onLayerChange,
  onResetLayers,
  collapsed,
  onToggleCollapsed,
  situation,
  onSituationVersion = () => undefined,
  onSituationLayer = () => undefined,
}: {
  viewState: DesignViewState;
  onPresetChange: (preset: ViewPresetId) => void;
  onLayerChange: (id: LayerId, visible: boolean) => void;
  onResetLayers: () => void;
  collapsed: boolean;
  onToggleCollapsed: () => void;
  situation?: SituationPanelModel;
  onSituationVersion?: (seriesKey: string, sourceId: string) => void;
  onSituationLayer?: (key: string, visible: boolean) => void;
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
        {situation && (
          <SituationGroup model={situation} query={query} onVersion={onSituationVersion} onLayer={onSituationLayer} />
        )}
      </div>

      <footer>
        <button type="button" className="secondary-button" onClick={onResetLayers}>Сбросить к пресету</button>
      </footer>
    </div>
  );
}
