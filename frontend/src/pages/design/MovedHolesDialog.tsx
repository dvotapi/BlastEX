// «Сгенерировать сетку» при сдвинутых скважинах (TASK-017, PR 2): сохранить сдвиги
// от узлов (сервер поставит скважины в новые узлы с тем же смещением) или
// сбросить их. «Применить» вариант подбора сдвиги сбрасывает — его текст
// подтверждения тоже здесь.
import { useEffect, useRef } from "react";
import { plural } from "../../lib/plural";

/** «3 скважины сдвинуты вручную». */
export function movedHolesText(count: number): string {
  const one = count % 10 === 1 && count % 100 !== 11;
  return `${count} ${plural(count, ["скважина", "скважины", "скважин"])} ${one ? "сдвинута" : "сдвинуты"} вручную`;
}

/** Подтверждение «Применить» варианта подбора при сдвинутых скважинах. */
export function movedResetConfirmText(count: number): string {
  const one = count % 10 === 1 && count % 100 !== 11;
  const reset = one ? "будет сброшен" : "будут сброшены";
  return `${count} ${plural(count, ["сдвиг", "сдвига", "сдвигов"])} вручную ${reset} — вернуть можно отменой (Ctrl+Z). Применить вариант?`;
}

export function MovedHolesDialog({
  count,
  onKeep,
  onReset,
  onCancel,
}: {
  count: number;
  onKeep: () => void;
  onReset: () => void;
  onCancel: () => void;
}) {
  const keepRef = useRef<HTMLButtonElement>(null);

  // Фокус — один раз при открытии: перерисовка страницы его не отбирает.
  useEffect(() => keepRef.current?.focus(), []);

  useEffect(() => {
    // Escape закрывает только окно: перехват до обработчиков плана и страницы.
    function onKey(e: KeyboardEvent) {
      if (e.key !== "Escape") return;
      e.preventDefault();
      e.stopImmediatePropagation();
      onCancel();
    }
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [onCancel]);

  return (
    <div className="moved-holes-backdrop" role="presentation" onClick={onCancel}>
      <div
        className="moved-holes-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="moved-holes-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="moved-holes-title">{movedHolesText(count)}</h2>
        <p>
          Сохранить — новая сетка поставит их в те же узлы с тем же сдвигом; скважина, узла которой в новой
          сетке нет, останется на месте ручной. Сбросить — все скважины встанут в узлы новой сетки.
        </p>
        <div className="moved-holes-actions">
          <button ref={keepRef} type="button" className="primary-button" onClick={onKeep}>Сохранить сдвиги</button>
          <button type="button" className="secondary-button" onClick={onReset}>Сбросить</button>
          <button type="button" className="secondary-button" onClick={onCancel}>Отмена</button>
        </div>
      </div>
    </div>
  );
}
