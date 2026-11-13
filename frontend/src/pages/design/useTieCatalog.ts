// Каталог номиналов ступеней (`GET /design/tie/catalog`): один запрос на
// сессию, неудача — следующая попытка при следующем монтировании.
import { useEffect, useState } from "react";
import { api } from "../../api/endpoints";
import type { TieCatalog } from "../../types/design";

let cached: TieCatalog | null = null;
let pending: Promise<TieCatalog> | null = null;

function loadCatalog(): Promise<TieCatalog> {
  if (!pending) {
    pending = api.design.tieCatalog().then(
      (catalog) => {
        cached = catalog;
        return catalog;
      },
      (reason) => {
        pending = null;
        throw reason;
      },
    );
  }
  return pending;
}

export function useTieCatalog(): TieCatalog | null {
  const [catalog, setCatalog] = useState<TieCatalog | null>(cached);
  useEffect(() => {
    if (catalog) return undefined;
    let alive = true;
    loadCatalog().then(
      (value) => {
        if (alive) setCatalog(value);
      },
      () => {},
    );
    return () => {
      alive = false;
    };
  }, [catalog]);
  return catalog;
}
