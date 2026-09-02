import type { LayerVisibility } from "./viewPresets";
import { contourLayersFromView, defaultDesignViewState } from "./viewPresets";

/** @deprecated Use LayerVisibility from viewPresets */
export type MapLayerId = "fill" | "crest" | "toe" | "face" | "holes";

/** @deprecated Use contourLayersFromView */
export type MapLayerVisibility = Record<MapLayerId, boolean>;

export const DEFAULT_MAP_LAYERS: MapLayerVisibility = contourLayersFromView(defaultDesignViewState().layers);

export function layersToMapLegend(layers: LayerVisibility): MapLayerVisibility {
  return contourLayersFromView(layers);
}
