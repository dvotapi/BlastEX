import { useEffect, useState } from "react";
import { api } from "../api/endpoints";

export type Features = {
  /** ML-слой: датасеты, калибровка, реестр моделей, дрифт, оптимизация. */
  intelligence: boolean;
  /** Паспорт на бурение (TASK-015): панель в «Отчёте» «Проектирования». */
  drill_passport: boolean;
};

const DISABLED: Features = { intelligence: false, drill_passport: false };

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
          setFeatures({ intelligence: Boolean(value.intelligence), drill_passport: Boolean(value.drill_passport) });
        }
      })
      .catch(() => {
        if (!cancelled) setFeatures(DISABLED);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return features;
}
