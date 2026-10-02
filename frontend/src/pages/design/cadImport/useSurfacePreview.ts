// Предпросмотр кровли блока (TASK-013, PR 3): сервер строит TIN, качество и
// объёмы на каждое изменение контура, ролей, исключений или подошвы.
import { api } from "../../../api/endpoints";
import type { CadSurfaceRequest, CadSurfaceResult } from "../../../types/cad";
import { usePreview, type Preview } from "./usePreview";

export function useSurfacePreview(
  sourceId: string,
  request: CadSurfaceRequest | null,
  fetcher: (sourceId: string, request: CadSurfaceRequest) => Promise<CadSurfaceResult> = api.cad.surface,
  version = 0,
): Preview<CadSurfaceResult> {
  return usePreview(sourceId, request, fetcher, version, "Не удалось построить кровлю.");
}
