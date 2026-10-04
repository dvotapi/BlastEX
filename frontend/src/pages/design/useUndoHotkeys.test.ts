// @vitest-environment jsdom
// Ctrl/Cmd+Z и Ctrl/Cmd+Shift+Z на странице «Проектирование»: вне полей ввода,
// и только пока проектная часть не заморожена — как кнопки ↶ ↷.
import { cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useUndoHotkeys } from "./useUndoHotkeys";

function press(init: KeyboardEventInit, target: EventTarget = window): KeyboardEvent {
  const event = new KeyboardEvent("keydown", { bubbles: true, cancelable: true, ...init });
  target.dispatchEvent(event);
  return event;
}

afterEach(() => {
  cleanup();
  document.body.replaceChildren();
});

describe("useUndoHotkeys", () => {
  it("Ctrl+Z — отмена, Ctrl+Shift+Z и Cmd+Shift+Z — повтор", () => {
    const dispatch = vi.fn();
    renderHook(() => useUndoHotkeys(dispatch, false));

    expect(press({ key: "z", ctrlKey: true }).defaultPrevented).toBe(true);
    press({ key: "Z", ctrlKey: true, shiftKey: true });
    press({ key: "z", metaKey: true, shiftKey: true });

    expect(dispatch.mock.calls).toEqual([[{ type: "UNDO" }], [{ type: "REDO" }], [{ type: "REDO" }]]);
  });

  it("замороженная проектная часть: клавиши не отменяют и не повторяют", () => {
    const dispatch = vi.fn();
    renderHook(() => useUndoHotkeys(dispatch, true));

    press({ key: "z", ctrlKey: true });
    press({ key: "z", metaKey: true, shiftKey: true });

    expect(dispatch).not.toHaveBeenCalled();
  });

  it("блокировка снята после рендера — клавиши снова работают", () => {
    const dispatch = vi.fn();
    const { rerender } = renderHook(({ locked }) => useUndoHotkeys(dispatch, locked), { initialProps: { locked: true } });

    press({ key: "z", ctrlKey: true });
    rerender({ locked: false });
    press({ key: "z", ctrlKey: true });

    expect(dispatch.mock.calls).toEqual([[{ type: "UNDO" }]]);
  });

  it("в поле ввода Ctrl+Z остаётся за полем", () => {
    const dispatch = vi.fn();
    renderHook(() => useUndoHotkeys(dispatch, false));
    const input = document.body.appendChild(document.createElement("input"));

    const event = press({ key: "z", ctrlKey: true }, input);

    expect(dispatch).not.toHaveBeenCalled();
    expect(event.defaultPrevented).toBe(false);
  });

  it("Z без модификатора и другие клавиши не трогает", () => {
    const dispatch = vi.fn();
    renderHook(() => useUndoHotkeys(dispatch, false));

    press({ key: "z" });
    press({ key: "y", ctrlKey: true });

    expect(dispatch).not.toHaveBeenCalled();
  });
});
