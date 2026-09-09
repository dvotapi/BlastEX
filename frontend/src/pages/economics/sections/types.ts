/**
 * Общие пропсы редакторов разделов конструктора сметы (задача 7).
 *
 * Один тип на все разделы: `BlockEconomicsPage` (задача 9) рендерит их по
 * каталогу `ESTIMATE_GROUPS`, не зная особенностей конкретного раздела —
 * особый пропс заводит только сам раздел (например, `onOpenDrillingPage`
 * у `DrillingSection`), а не этот общий тип.
 */
import type { BlockEconomics, ModelDefaults, ModelParameters } from "../../../types/blockEconomics";
import type { EstimateGroup } from "../estimateModel";

export type SectionEditorProps = {
  group: EstimateGroup;
  params: ModelParameters;
  defaults: ModelDefaults;
  /** null — расчёт ещё не пришёл: первая загрузка страницы или параметры уже изменились, а ответ ещё летит. */
  economics: BlockEconomics | null;
  volume: number | null;
  canEdit: boolean;
  onChange: (patch: Partial<ModelParameters>) => void;
};
