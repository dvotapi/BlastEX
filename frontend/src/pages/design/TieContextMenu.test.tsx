// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TieContextMenu } from "./TieContextMenu";

afterEach(cleanup);

function renderMenu() {
  const props = {
    menu: { tieId: "sc-1-01-1-02", fromHole: "1-01", toHole: "1-02", delayMs: 42, x: 10, y: 20 },
    nominals: [17, 25, 42, 67, 109],
    onClose: vi.fn(),
    onSetDelay: vi.fn(),
    onReverse: vi.fn(),
    onRemove: vi.fn(),
  };
  render(<TieContextMenu {...props} />);
  return props;
}

describe("меню связи", () => {
  it("ступень из номиналов, текущая отмечена", () => {
    const props = renderMenu();
    expect(screen.getByRole("menu", { name: "Меню связи 1-01 → 1-02" })).toBeInTheDocument();
    expect(screen.getByRole("menuitemradio", { name: "42" })).toHaveAttribute("aria-checked", "true");
    fireEvent.click(screen.getByRole("menuitemradio", { name: "67" }));
    expect(props.onSetDelay).toHaveBeenCalledWith("sc-1-01-1-02", 67);
    expect(props.onClose).toHaveBeenCalled();
  });

  it("разворот и удаление", () => {
    const props = renderMenu();
    fireEvent.click(screen.getByRole("menuitem", { name: "Развернуть направление" }));
    expect(props.onReverse).toHaveBeenCalledWith("sc-1-01-1-02");
    fireEvent.click(screen.getByRole("menuitem", { name: "Удалить" }));
    expect(props.onRemove).toHaveBeenCalledWith("sc-1-01-1-02");
  });
});
