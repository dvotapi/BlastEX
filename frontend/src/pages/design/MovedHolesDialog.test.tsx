// @vitest-environment jsdom
// «Построить сетку» и «Применить» при сдвинутых скважинах (TASK-017, PR 2).
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Hole } from "../../types/design";
import { patternRequestHoles } from "./holeMove";
import { MovedHolesDialog, movedHolesText, movedResetConfirmText } from "./MovedHolesDialog";

afterEach(cleanup);

function hole(id: string, extra: Partial<Hole> = {}): Hole {
  return { id, source: "generated", collar: { x: 0, y: 0, z: 0 }, toe: { x: 0, y: 0, z: -10 }, ...extra } as Hole;
}

describe("MovedHolesDialog", () => {
  it("заголовок с числом и три кнопки", () => {
    const props = { onKeep: vi.fn(), onReset: vi.fn(), onCancel: vi.fn() };
    render(<MovedHolesDialog count={3} {...props} />);
    expect(screen.getByRole("dialog", { name: "3 скважины сдвинуты вручную" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Сохранить сдвиги" }));
    fireEvent.click(screen.getByRole("button", { name: "Сбросить" }));
    fireEvent.click(screen.getByRole("button", { name: "Отмена" }));
    fireEvent.keyDown(window, { key: "Escape" });
    expect(props.onKeep).toHaveBeenCalledTimes(1);
    expect(props.onReset).toHaveBeenCalledTimes(1);
    expect(props.onCancel).toHaveBeenCalledTimes(2);
  });

  it("перерисовка не отбирает фокус; Escape не доходит до страницы", () => {
    const props = { onKeep: vi.fn(), onReset: vi.fn() };
    const view = render(<MovedHolesDialog count={2} {...props} onCancel={vi.fn()} />);
    const reset = screen.getByRole("button", { name: "Сбросить" });
    reset.focus();
    view.rerender(<MovedHolesDialog count={2} {...props} onCancel={vi.fn()} />);
    expect(document.activeElement).toBe(reset);

    const page = vi.fn();
    window.addEventListener("keydown", page);
    fireEvent.keyDown(window, { key: "Escape" });
    window.removeEventListener("keydown", page);
    expect(page).not.toHaveBeenCalled();
  });

  it("склонение", () => {
    expect(movedHolesText(1)).toBe("1 скважина сдвинута вручную");
    expect(movedHolesText(5)).toBe("5 скважин сдвинуты вручную");
    expect(movedResetConfirmText(1)).toMatch(/^1 сдвиг вручную будет сброшен — /);
    expect(movedResetConfirmText(2)).toMatch(/^2 сдвига вручную будут сброшены — .*Применить вариант\?$/);
    expect(movedResetConfirmText(11)).toMatch(/^11 сдвигов вручную будут сброшены/);
  });
});

describe("patternRequestHoles", () => {
  const moved = hole("1-01", { manual: ["xy", "length"], manual_offset: { node_x: 0, node_y: 0, along: 1, across: 0 } });
  const holes = [moved, hole("1-02"), hole("M-1", { source: "manual" })];

  it("«Сохранить» — скважины как есть", () => {
    expect(patternRequestHoles(holes, true)).toBe(holes);
  });

  it("«Сбросить» — без сдвигов: сервер поставит все в узлы", () => {
    const sent = patternRequestHoles(holes, false);
    expect(sent[0].manual).toEqual(["length"]);
    expect("manual_offset" in sent[0]).toBe(false);
    expect(sent[1]).toBe(holes[1]);
    expect(sent[2]).toBe(holes[2]);
  });
});
