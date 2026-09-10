/**
 * Координаты всплывающей панели, привязанной к кнопке.
 *
 * Панели строк сметы (список справочника, меню «⋯») нельзя рисовать
 * `position:absolute` внутри строки: ячейка названия обрезает содержимое по
 * многоточию (`overflow:hidden`), и список оказывался виден на высоту строки —
 * то есть не виден вовсе. Панель рисуется порталом в `document.body` с
 * `position:fixed`, а координаты считает этот хук по прямоугольнику кнопки.
 *
 * Возвращает `null`, пока панель закрыта или размер ещё не измерен: вызывающий
 * код в этот момент ничего не рисует, поэтому панель не мигает в углу экрана
 * до первого измерения.
 */
import { useCallback, useLayoutEffect, useState, type RefObject } from "react";

/** Зазор между кнопкой и панелью и минимальный отступ от края окна. */
const GAP = 4;
const EDGE = 8;

export type AnchoredPosition = { top: number; left: number; minWidth: number };

export function useAnchoredPosition(
  anchorRef: RefObject<HTMLElement | null>,
  open: boolean,
  /** `start` — левый край панели по левому краю кнопки, `end` — правый по правому. */
  align: "start" | "end" = "start",
  /** Наименьшая ширина панели: она же уходит в `minWidth` результата. */
  width = 0,
  /**
   * Ожидаемая высота панели — по ней решается, открыть её вниз или вверх.
   * Своя у каждой панели: список справочника высокий, меню строки низкое, и
   * общая величина заставляла бы короткое меню разворачиваться вверх там,
   * где ему хватало места снизу.
   */
  height = 280,
): AnchoredPosition | null {
  const [position, setPosition] = useState<AnchoredPosition | null>(null);

  const measure = useCallback(() => {
    const anchor = anchorRef.current;
    if (!anchor) return;
    const rect = anchor.getBoundingClientRect();

    // jsdom не считает раскладку: все прямоугольники нулевые. Считать по ним
    // переворот и прижатие к краям бессмысленно — тесты проверяют поведение
    // списка, а не геометрию, поэтому просто отдаём нули.
    if (rect.width === 0 && rect.height === 0) {
      setPosition({ top: 0, left: 0, minWidth: width });
      return;
    }

    const below = window.innerHeight - rect.bottom;
    const flipUp = below < height && rect.top > below;
    // Зажим по верхнему краю обязателен: при развороте вверх над кнопкой
    // может не быть `height` пикселей, и панель уезжала за край окна вместе
    // с верхними пунктами списка.
    const top = flipUp ? Math.max(rect.top - GAP - height, EDGE) : rect.bottom + GAP;

    const panelWidth = Math.max(width, rect.width);
    const rawLeft = align === "end" ? rect.right - panelWidth : rect.left;
    const left = Math.min(Math.max(rawLeft, EDGE), Math.max(EDGE, window.innerWidth - EDGE - panelWidth));

    setPosition({ top, left, minWidth: panelWidth });
  }, [align, anchorRef, height, width]);

  useLayoutEffect(() => {
    if (!open) {
      setPosition(null);
      return undefined;
    }
    measure();
    // Прокрутка любого предка, а не только окна: `capture` ловит события
    // прокрутки на пути вниз, обычный слушатель на `window` их не увидит,
    // потому что `scroll` от элемента не всплывает.
    window.addEventListener("scroll", measure, true);
    window.addEventListener("resize", measure);
    return () => {
      window.removeEventListener("scroll", measure, true);
      window.removeEventListener("resize", measure);
    };
  }, [measure, open]);

  return position;
}
