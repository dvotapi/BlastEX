// Предпросмотр контура блока (TASK-013, PR 2): сервер пересчитывает контур
// на каждое изменение способа или участков (`usePreview`).
import { api } from "../../../api/endpoints";
import type { CadContourRequest, CadContourResult } from "../../../types/cad";
import { usePreview, type Preview } from "./usePreview";

export function useContourPreview(
  sourceId: string,
  request: CadContourRequest | null,
  fetcher: (sourceId: string, request: CadContourRequest) => Promise<CadContourResult> = api.cad.contour,
  version = 0,
): Preview<CadContourResult> {
  return usePreview(sourceId, request, fetcher, version, "Не удалось построить контур.");
}
