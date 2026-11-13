// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TiePalette } from "./TiePalette";
import { nominalForKey, tieToolForKey } from "./tieSteps";
import { TEST_TIE_CATALOG } from "./testing/tieCatalog";

afterEach(cleanup);

function renderPalette(over: Partial<Parameters<typeof TiePalette>[0]> = {}) {
  const props = {
    catalog: TEST_TIE_CATALOG.systems.nonel,
    tool: "tie" as const,
    onToolChange: vi.fn(),
    activeMs: 25,
    onActiveMsChange: vi.fn(),
    downholeMs: 500,
    onDownholeMsChange: vi.fn(),
    ...over,
  };
  render(<TiePalette {...props} />);
  return props;
}

describe("палитра коммутации", () => {
  it("номиналы системы, активный выделен, клик меняет активный", () => {
    const props = renderPalette();
    const group = screen.getByRole("group", { name: "Ступень, мс" });
    const buttons = Array.from(group.querySelectorAll("button")).map((b) => b.textContent);
    expect(buttons).toEqual(["17", "25", "42", "67", "109"]);
    expect(screen.getByRole("button", { name: "25" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "42" }));
    expect(props.onActiveMsChange).toHaveBeenCalledWith(42);
  });

  it("ДШ — реле, без поля «своё»", () => {
    renderPalette({ catalog: TEST_TIE_CATALOG.systems.detcord, activeMs: 20, downholeMs: 0 });
    expect(screen.getByRole("button", { name: "35" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Своя ступень, мс")).not.toBeInTheDocument();
  });

  it("электронная — поле «своё, мс»", () => {
    const props = renderPalette({ catalog: TEST_TIE_CATALOG.systems.electronic, activeMs: 30, downholeMs: 0 });
    const input = screen.getByLabelText("Своя ступень, мс") as HTMLInputElement;
    expect(input.value).toBe("30");
    fireEvent.change(input, { target: { value: "33" } });
    expect(props.onActiveMsChange).toHaveBeenCalledWith(33);
  });

  it("инструменты переключаются кнопками; клавиши T/D/S/H и цифры", () => {
    const props = renderPalette();
    fireEvent.click(screen.getByRole("button", { name: /Ступень D/ }));
    expect(props.onToolChange).toHaveBeenCalledWith("step");
    expect(tieToolForKey("T")).toBe("tie");
    expect(tieToolForKey("в")).toBe("step");
    expect(tieToolForKey("s")).toBe("starter");
    expect(tieToolForKey("р")).toBe("downhole");
    expect(tieToolForKey("x")).toBeNull();
    expect(nominalForKey("3", [17, 25, 42, 67, 109])).toBe(42);
    expect(nominalForKey("6", [17, 25, 42, 67, 109])).toBeNull();
  });

  it("замедление в скважине — номиналы СИНВ", () => {
    const props = renderPalette();
    fireEvent.change(screen.getByLabelText("Замедление в скважине, мс"), { target: { value: "700" } });
    expect(props.onDownholeMsChange).toHaveBeenCalledWith(700);
  });
});
