import { useEffect, useState } from "react";
import { api } from "../api/endpoints";

export type Features = {
  /** ML-слой: датасеты, калибровка, реестр моделей, дрифт, оптимизация. */
  intelligence: boolean;
};

const DISABLED: Features = { intelligence: false };

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
        if (!cancelled) setFeatures({ intelligence: Boolean(value.intelligence) });
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
