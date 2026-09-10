// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RowMenu } from "./RowMenu";

afterEach(cleanup);

describe("RowMenu", () => {
  it("без пунктов не рисует даже кнопку", () => {
    render(<RowMenu items={[]} label="Действия: строка 1.1" />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("список не обрезается предком: он рисуется порталом в body", async () => {
    render(
      <div style={{ overflow: "hidden", height: 20 }}>
        <RowMenu items={[{ label: "Убрать", onSelect: () => {} }]} label="Действия: строка 1.1" />
      </div>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Действия: строка 1.1" }));

    const menu = screen.getByRole("menu");
    expect(menu.closest(".row-menu")).toBeNull();
    expect(menu.parentElement).toBe(document.body);
  });

  it("выбор пункта закрывает меню и зовёт действие", async () => {
    const onSelect = vi.fn();
    render(<RowMenu items={[{ label: "Убрать", onSelect }]} label="Действия: строка 1.1" />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Действия: строка 1.1" }));
    await user.click(screen.getByRole("menuitem", { name: "Убрать" }));

    expect(onSelect).toHaveBeenCalledOnce();
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("пункт-раскрывашка называет своё состояние и управляемый узел", async () => {
    render(
      <RowMenu
        items={[{ label: "Формула", onSelect: () => {}, expanded: false, controls: "panel-1" }]}
        label="Действия: строка 1.1"
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Действия: строка 1.1" }));

    const item = screen.getByRole("menuitem", { name: "Формула" });
    expect(item).toHaveAttribute("aria-expanded", "false");
    expect(item).toHaveAttribute("aria-controls", "panel-1");
  });

  it("Escape закрывает меню и возвращает фокус кнопке", async () => {
    render(<RowMenu items={[{ label: "Убрать", onSelect: () => {} }]} label="Действия: строка 1.1" />);
    const user = userEvent.setup();
    const trigger = screen.getByRole("button", { name: "Действия: строка 1.1" });
    await user.click(trigger);
    expect(screen.getByRole("menu")).toBeInTheDocument();

    await user.keyboard("{Escape}");

    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });
});
