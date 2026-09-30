/**
 * Подпись «откуда настройки модели» для панели «Кусковатость». Сами настройки
 * живут на листе «Расчёт» за объектом работ; «Проектирование» их только
 * читает, поэтому здесь нет полей ввода — только строка источника.
 */
import type { FragmentationPredictResponse } from "../../types/design";

export function isLegacyFragmentationModel(model: string): boolean {
  return model.endsWith("_legacy");
}

export function settingsSourceLabel(result: Pick<FragmentationPredictResponse, "model" | "settings">): string {
  if (isLegacyFragmentationModel(result.model)) return "Старая модель: настройки объекта не применяются";
  const settings = result.settings;
  if (settings?.source === "request") return "Настройки модели: заданы в запросе";
  if (settings?.source === "work_object") return `Настройки модели: объект работ «${settings.work_object_name}»`;
  if (settings?.work_object_name) {
    return settings.warnings.length > 0
      ? `Настройки модели: умолчания — настройки объекта «${settings.work_object_name}» не прочитаны`
      : `Настройки модели: умолчания — у объекта «${settings.work_object_name}» они не сохранены`;
  }
  return "Настройки модели: умолчания";
}
