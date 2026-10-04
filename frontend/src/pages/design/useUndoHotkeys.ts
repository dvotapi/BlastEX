// Ctrl/Cmd+Z — отмена, Ctrl/Cmd+Shift+Z — повтор. В полях ввода клавиши
// остаются за полем; при закрытой истории (`historyLocked`) клавиши молчат —
// так же, как кнопки ↶ ↷ в шапке.
import { useEffect } from "react";

export function useUndoHotkeys(dispatch: (action: { type: "UNDO" } | { type: "REDO" }) => void, locked: boolean): void {
  useEffect(() => {
    if (locked) return;
    function onKeyDown(e: KeyboardEvent) {
      const target = e.target as HTMLElement;
      const typing = target.tagName === "INPUT" || target.tagName === "SELECT" || target.tagName === "TEXTAREA";
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z" && !typing) {
        e.preventDefault();
        dispatch({ type: e.shiftKey ? "REDO" : "UNDO" });
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [dispatch, locked]);
}
