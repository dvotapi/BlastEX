import { createContext, useContext, type ReactNode } from "react";

/**
 * DOM-узел в шапке приложения (`.topbar`), куда страница может перенести
 * свою полосу инструментов через `createPortal` — так лист «Расчёт» кладёт
 * юнит, объект и статус автосохранения в верхнюю панель вместо пустующего
 * места рядом с заголовком (см. `AppShell.tsx`, `CalcTopStrip.tsx`).
 *
 * Узел передаётся, а не создаётся самой страницей: слот один на всё
 * приложение и живёт в шапке независимо от того, какая страница открыта.
 */
const TopbarSlotContext = createContext<HTMLDivElement | null>(null);
const TopbarTitleSlotContext = createContext<HTMLDivElement | null>(null);
const TopbarTrailingSlotContext = createContext<HTMLDivElement | null>(null);

export function TopbarSlotProvider({
  slot,
  titleSlot,
  trailingSlot,
  children,
}: {
  slot: HTMLDivElement | null;
  /** Узел рядом с заголовком страницы — см. `useTopbarTitleSlot`. */
  titleSlot: HTMLDivElement | null;
  /** Узел после кнопки «Выйти» — см. `useTopbarTrailingSlot`. */
  trailingSlot: HTMLDivElement | null;
  children: ReactNode;
}) {
  return (
    <TopbarSlotContext.Provider value={slot}>
      <TopbarTitleSlotContext.Provider value={titleSlot}>
        <TopbarTrailingSlotContext.Provider value={trailingSlot}>{children}</TopbarTrailingSlotContext.Provider>
      </TopbarTitleSlotContext.Provider>
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

/**
 * Узел в самом правом углу шапки, после кнопки «Выйти» — для круглой кнопки
 * справки листа «Расчёт». Общий слот (`useTopbarSlot`) стоит до «Выйти», и
 * кнопка в нём оказалась бы посреди полосы.
 */
export function useTopbarTrailingSlot(): HTMLDivElement | null {
  return useContext(TopbarTrailingSlotContext);
}
