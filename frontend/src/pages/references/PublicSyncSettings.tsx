import { useState } from "react";
import { api } from "../../api/endpoints";
import type { PublicSyncSettings } from "../../types/economics";
import { settingsPatch } from "./publicSettings";

/**
 * Настройки обмена с журналом project1.public: общий переключатель и зеркала
 * разделов. Панель только у администратора — остальным страница настройки не
 * загружает.
 *
 * Оптимистичного состояния нет: переключатели рисуются по последнему ответу
 * сервера и меняются только после успешного сохранения. Поэтому отказ базы
 * (нет прав на запись в public) сам по себе оставляет панель в том виде, какой
 * подтвердил сервер, — «откатывать» нечего.
 */
export function PublicSyncSettingsPanel({
  settings,
  sectionLabel,
  onChange,
  onSaved,
}: {
  settings: PublicSyncSettings | null;
  sectionLabel: (section: string) => string;
  onChange: (settings: PublicSyncSettings) => void;
  onSaved: () => void;
}) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  if (!settings) return null;

  const save = async (change: { exchange_enabled?: boolean; section?: string; enabled?: boolean }) => {
    setSaving(true);
    setError("");
    try {
      onChange(await api.economics.savePublicSettings(settingsPatch(settings, change)));
      onSaved();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось сохранить настройки обмена.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <details className="ref-public-settings">
      <summary>Обмен с project1.public</summary>

      <label>
        <input
          type="checkbox"
          checked={settings.exchange_enabled}
          disabled={saving}
          onChange={(event) => void save({ exchange_enabled: event.target.checked })}
        />
        Обмен с журналом project1.public
      </label>
      <p className="page-caption">
        Опубликованные контрагенты, объекты, техника, СИ и буровой инструмент записываются в таблицы
        журнала.
      </p>

      <p className="ref-public-settings-title">Выгружать в project1.public</p>
      <div className="ref-public-settings-list">
        {settings.mirrorable_sections.map((section) => (
          <label key={section}>
            <input
              type="checkbox"
              checked={settings.mirror_sections[section] ?? false}
              disabled={saving}
              onChange={(event) => void save({ section, enabled: event.target.checked })}
            />
            {sectionLabel(section)}
          </label>
        ))}
      </div>

      {error && (
        <p className="ref-public-settings-error" role="alert">
          {error}
        </p>
      )}
    </details>
  );
}
