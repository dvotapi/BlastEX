export type MapLayerId = "fill" | "crest" | "toe" | "face" | "holes";

export type MapLayerVisibility = Record<MapLayerId, boolean>;

/** @deprecated Используйте contourLayersFromView из viewPresets. */
export { contourLayersFromView } from "./viewPresets";

export const DEFAULT_MAP_LAYERS: MapLayerVisibility = {
  fill: true,
  crest: true,
  toe: true,
  face: true,
  holes: true,
};

const LAYER_ITEMS: Array<{ id: MapLayerId; label: string; swatch: string }> = [
  { id: "crest", label: "Верхняя бровка", swatch: "crest" },
  { id: "toe", label: "Нижняя бровка", swatch: "toe" },
  { id: "face", label: "Откос", swatch: "face" },
  { id: "holes", label: "Скважины", swatch: "holes" },
  { id: "fill", label: "Заливка контура", swatch: "fill" },
];

export function MapLegend({
  layers,
  onChange,
}: {
  layers: MapLayerVisibility;
  onChange: (next: MapLayerVisibility) => void;
}) {
  return (
    <div className="map-layer-legend" aria-label="Легенда карты">
      <b>Слои</b>
      {LAYER_ITEMS.map((item) => (
        <label key={item.id}>
          <input
            type="checkbox"
            checked={layers[item.id]}
            onChange={(e) => onChange({ ...layers, [item.id]: e.target.checked })}
          />
          <i className={`legend-swatch ${item.swatch}`} aria-hidden="true" />
          <span>{item.label}</span>
        </label>
      ))}
    </div>
  );
}
