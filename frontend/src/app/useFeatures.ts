import { useEffect, useState } from "react";
import { api } from "../api/endpoints";

export type Features = {
  /** ML-слой: датасеты, калибровка, реестр моделей, дрифт, оптимизация. */
  intelligence: boolean;
  /** Паспорт на бурение (TASK-015): панель в «Отчёте» «Проектирования». */
  drill_passport: boolean;
  /** Проект МВ по форме ВМ.09.03 (TASK-018): окно проекта и слои дня взрыва. */
  mass_blast_v2: boolean;
  /** Ответ сервера получен (или не получен с ошибкой): до него разделы не рисуются. */
  loaded: boolean;
};

const DISABLED: Features = { intelligence: false, drill_passport: false, mass_blast_v2: false, loaded: false };

/**
 * Состав включённых модулей установки.
 *
 * Пока ответ не пришёл, разделы считаются выключенными: лучше показать их с
 * задержкой, чем нарисовать раздел, который сервер отдаст с кодом 501.
 */
export function useFeatures(): Features {
  const [features, setFeatures] = useState<Features>(DISABLED);

  useEffect(() => {
    let cancelled = false;
    api
      .features()
      .then((value) => {
        if (!cancelled) {
          setFeatures({
            intelligence: Boolean(value.intelligence),
            drill_passport: Boolean(value.drill_passport),
            mass_blast_v2: Boolean(value.mass_blast_v2),
            loaded: true,
          });
        }
      })
      .catch(() => {
        if (!cancelled) setFeatures({ ...DISABLED, loaded: true });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return features;
}
