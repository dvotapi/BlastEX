import { useCallback, type RefCallback } from "react";

/**
 * Пишет высоту DOM-узла в CSS-переменную на его родителе и обновляет её
 * `ResizeObserver`-ом — для липких блоков, которым надо отступить на высоту
 * другого липкого блока над ними. Без React-состояния: изменение высоты
 * полосы — вопрос раскладки, а не данных, и перерисовывать ради него всё
 * поддерево страницы незачем. Возвращает callback-ref; React 19 вызывает
 * возвращённую из него функцию очистки при размонтировании узла, и она
 * снимает переменную с родителя.
 */
export function useHeightVariable(name: string): RefCallback<HTMLElement> {
  return useCallback(
    (node: HTMLElement | null) => {
      if (!node) return;
      const scope = node.parentElement ?? node;
      const apply = () => scope.style.setProperty(name, `${node.offsetHeight}px`);
      apply();
      const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(apply);
      observer?.observe(node);
      return () => {
        observer?.disconnect();
        scope.style.removeProperty(name);
      };
    },
    [name],
  );
}
