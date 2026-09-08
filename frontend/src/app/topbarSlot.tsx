import { createContext, useContext, type ReactNode } from "react";

/**
 * DOM-узел в шапке приложения (`.topbar`), куда страница может перенести
 * свою полосу инструментов через `createPortal` — так лист «Расчёт» кладёт
 * команду, объект и плашки результата в верхнюю панель вместо пустующего
 * места рядом с заголовком (см. `AppShell.tsx`, `CalcTopStrip.tsx`).
 *
 * Узел передаётся, а не создаётся самой страницей: слот один на всё
 * приложение и живёт в шапке независимо от того, какая страница открыта.
 */
const TopbarSlotContext = createContext<HTMLDivElement | null>(null);
const TopbarTitleSlotContext = createContext<HTMLDivElement | null>(null);

export function TopbarSlotProvider({
  slot,
  titleSlot,
  children,
}: {
  slot: HTMLDivElement | null;
  /** Узел рядом с заголовком страницы — см. `useTopbarTitleSlot`. */
  titleSlot: HTMLDivElement | null;
  children: ReactNode;
}) {
  return (
    <TopbarSlotContext.Provider value={slot}>
      <TopbarTitleSlotContext.Provider value={titleSlot}>{children}</TopbarTitleSlotContext.Provider>
    </TopbarSlotContext.Provider>
  );
}

/**
 * Узел слота в шапке, если он уже смонтирован, иначе `null` — тогда
 * содержимое рисуется на своём обычном месте на странице, как до появления
 * слота (например, в тестах компонентов без `AppShell`).
 */
export function useTopbarSlot(): HTMLDivElement | null {
  return useContext(TopbarSlotContext);
}

/**
 * Узел сразу справа от заголовка страницы (в той же строке, что `TITLES[page]`
 * в `AppShell.tsx`) — для кнопок, которые относятся к заголовку, а не к
 * панели инструментов справа (для неё есть `useTopbarSlot`).
 */
export function useTopbarTitleSlot(): HTMLDivElement | null {
  return useContext(TopbarTitleSlotContext);
}
