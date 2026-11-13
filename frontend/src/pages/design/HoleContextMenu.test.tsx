// @vitest-environment jsdom
// Меню скважины (TASK-017, PR 2): «Вернуть в узел сетки» — у сдвинутой; для
// выделенных — все сдвинутые из выделения.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { HoleContextMenu } from "./HoleContextMenu";

afterEach(cleanup);

function renderMenu(returnIds: string[]) {
  const onReturnToNode = vi.fn();
  render(
    <HoleContextMenu
      menu={{ holeId: "1-01", x: 10, y: 10 }}
      onClose={vi.fn()}
      onOpenInspector={vi.fn()}
      onToggleEnabled={vi.fn()}
      onToggleStarter={vi.fn()}
      onCopyParams={vi.fn()}
      onZoomToHole={vi.fn()}
      onReturnToNode={onReturnToNode}
      returnToNodeIds={returnIds}
      isStarter={false}
      enabled
    />,
  );
  return onReturnToNode;
}

describe("HoleContextMenu: «Вернуть в узел сетки»", () => {
  it("у одной сдвинутой — пункт без числа", () => {
    const onReturn = renderMenu(["1-01"]);
    fireEvent.click(screen.getByRole("menuitem", { name: "Вернуть в узел сетки" }));
    expect(onReturn).toHaveBeenCalledWith(["1-01"]);
  });

  it("у выделенных — число сдвинутых", () => {
    const onReturn = renderMenu(["1-01", "1-02"]);
    fireEvent.click(screen.getByRole("menuitem", { name: "Вернуть в узел сетки (2)" }));
    expect(onReturn).toHaveBeenCalledWith(["1-01", "1-02"]);
  });

  it("несдвинутой — пункта нет", () => {
    renderMenu([]);
    expect(screen.queryByRole("menuitem", { name: /Вернуть в узел/ })).toBeNull();
  });
});
