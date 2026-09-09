import { useCallback, useState, type RefCallback } from "react";

/**
 * Высота DOM-узла в пикселях, обновляемая `ResizeObserver`-ом: для липких
 * блоков, которым надо отступить на высоту другого липкого блока над ними.
 * Возвращает callback-ref (узел может смонтироваться позже хука) и текущую
 * высоту; до монтирования — 0. React 19 вызывает функцию очистки,
 * возвращённую из ref, при размонтировании узла.
 */
export function useElementHeight(): [RefCallback<HTMLElement>, number] {
  const [height, setHeight] = useState(0);
  const ref = useCallback((node: HTMLElement | null) => {
    if (!node) return;
    setHeight(node.offsetHeight);
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => setHeight(node.offsetHeight));
    observer.observe(node);
    return () => {
      observer.disconnect();
      setHeight(0);
    };
  }, []);
  return [ref, height];
}
