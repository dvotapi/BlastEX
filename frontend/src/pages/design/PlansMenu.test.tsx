// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { DesignSummary } from "../../types/design";
import { PlansMenu } from "./PlansMenu";

const plans = [
  { design_id: "d66", name: "Блок 66", lifecycle_status: "draft", hole_count: 196, updated_at: "2026-11-12T10:00:00Z" },
  { design_id: "d67", name: "Блок 67", lifecycle_status: "approved", hole_count: 120, updated_at: "2026-11-11T10:00:00Z", surveyed: true },
] as DesignSummary[];

function setup(unsaved = false) {
  const handlers = { onOpen: vi.fn(), onDelete: vi.fn(), onNew: vi.fn() };
  render(<PlansMenu plans={plans} currentDesignId="d66" unsaved={unsaved} busy={false} {...handlers} />);
  return handlers;
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("PlansMenu", () => {
  it("список закрыт, пока не нажата «Проекты»; открытие проекта закрывает меню", async () => {
    const { onOpen } = setup();
    expect(screen.queryByRole("dialog")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: /Проекты/ }));
    await userEvent.click(screen.getByRole("button", { name: /^Блок 67/ }));
    expect(onOpen).toHaveBeenCalledWith("d67");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("стадия проекта в строке: «предварительный» или «по съёмке»", async () => {
    setup();
    await userEvent.click(screen.getByRole("button", { name: /Проекты/ }));
    expect(screen.getByRole("button", { name: /^Блок 66/ }).textContent).toContain("черновик · предварительный ·");
    expect(screen.getByRole("button", { name: /^Блок 67/ }).textContent).toContain("утверждён · по съёмке ·");
  });

  it("новый проект и закрытие по Escape", async () => {
    const { onNew } = setup();
    await userEvent.click(screen.getByRole("button", { name: /Проекты/ }));
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: /Проекты/ }));
    await userEvent.click(screen.getByRole("button", { name: "Новый проект" }));
    expect(onNew).toHaveBeenCalled();
  });

  it("удаление — только после подтверждения и только для разрешённого статуса", async () => {
    const { onDelete } = setup();
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    await userEvent.click(screen.getByRole("button", { name: /Проекты/ }));
    expect(screen.getByRole("button", { name: "Удалить «Блок 67»" })).toBeDisabled();
    const remove = screen.getByRole("button", { name: "Удалить «Блок 66»" });
    await userEvent.click(remove);
    expect(onDelete).not.toHaveBeenCalled();
    await userEvent.click(remove);
    expect(confirm).toHaveBeenCalledTimes(2);
    expect(onDelete).toHaveBeenCalledWith("d66");
  });

  it("при несохранённых правках открыть другой проект — только с подтверждением", async () => {
    const { onOpen, onNew } = setup(true);
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    await userEvent.click(screen.getByRole("button", { name: /Проекты/ }));
    await userEvent.click(screen.getByRole("button", { name: /^Блок 67/ }));
    expect(onOpen).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Новый проект" }));
    expect(onNew).toHaveBeenCalled();
    expect(confirm).toHaveBeenCalledTimes(2);
  });
});
