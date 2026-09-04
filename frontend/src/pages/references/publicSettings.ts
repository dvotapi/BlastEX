import type { PublicSyncSettings } from "../../types/economics";

/** Тело `PUT`: сервер ждёт состояние целиком, а не изменённое поле. */
export type PublicSyncSettingsPatch = {
  exchange_enabled: boolean;
  mirror_sections: Record<string, boolean>;
};

/**
 * Тело запроса настроек: текущее состояние с одним изменением — флагом обмена
 * или зеркалом раздела.
 *
 * Зеркала собираются по `mirrorable_sections`, а не по ключам ответа: порядок
 * и состав разделов задаёт сервер, а раздел, которого он зеркалить не даёт
 * (например сопоставляемый), в теле не появится и не вызовет 422.
 */
export function settingsPatch(
  current: PublicSyncSettings,
  change: { exchange_enabled?: boolean; section?: string; enabled?: boolean },
): PublicSyncSettingsPatch {
  const mirrors: Record<string, boolean> = {};
  for (const section of current.mirrorable_sections) {
    const enabled =
      change.section === section && change.enabled !== undefined
        ? change.enabled
        : (current.mirror_sections[section] ?? false);
    mirrors[section] = enabled;
  }
  return {
    exchange_enabled: change.exchange_enabled ?? current.exchange_enabled,
    mirror_sections: mirrors,
  };
}
