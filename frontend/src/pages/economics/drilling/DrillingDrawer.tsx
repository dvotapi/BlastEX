/**
 * Выдвижная панель с разложением стоимости метра бурения (`DrillingBreakdown`)
 * поверх сметы — не модальная: смету за панелью видно и можно листать дальше.
 *
 * Не модальная не значит недоступная с клавиатуры: панель забирает фокус при
 * открытии, закрывается по Escape и возвращает фокус на кнопку, которая её
 * открыла.
 */
import { useEffect, useRef } from "react";
import { DrillingBreakdown } from "../DrillingBreakdown";
import type { BlockEconomics } from "../../../types/blockEconomics";

export function DrillingDrawer({ economics, onClose }: { economics: BlockEconomics; onClose: () => void }) {
  const closeRef = useRef<HTMLButtonElement>(null);

  // Забрать фокус при открытии и вернуть его туда, откуда пришли. Без
  // возврата закрытие по Escape размонтирует кнопку вместе с фокусом, и он
  // падает на тело документа: путь по клавиатуре приходится начинать заново.
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    return () => {
      // `isConnected`: открывшая кнопка могла исчезнуть вместе со строкой,
      // например при смене способа исполнения бурения.
      if (opener?.isConnected) opener.focus();
    };
  }, []);

  // Слушатель на документе, а не на самой панели: Escape должен закрывать её
  // и тогда, когда фокус успел уйти на страницу за панелью.
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <aside className="drilling-drawer" role="dialog" aria-modal="false" aria-label="Расчёт бурения">
      <button ref={closeRef} type="button" className="drilling-drawer-close" aria-label="Закрыть" onClick={onClose}>
        ×
      </button>
      <DrillingBreakdown economics={economics} />
    </aside>
  );
}
