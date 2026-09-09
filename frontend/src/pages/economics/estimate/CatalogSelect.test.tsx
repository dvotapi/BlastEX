// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CatalogSelect } from "./CatalogSelect";

const options = [
  { code: "GRANULIT", name: "Гранулит РП", price: 46, unit: "кг" },
  { code: "SFERIT", name: "Сферит ДТ", price: 150, unit: "кг" },
  { code: "BEREZIT", name: "Березит Э-100", price: 54.2, unit: "кг" },
];

// Автоочистка RTL держится на глобальном `afterEach`, а в конфиге
// vitest `globals` выключен (как и во всех тестах проекта) — без явного
// вызова три рендера с одинаковым `label` копятся в одном document.body.
afterEach(cleanup);

describe("CatalogSelect", () => {
  it("ищет по подстроке и выбирает клавиатурой", async () => {
    const onChange = vi.fn();
    render(<CatalogSelect id="ex" label="Основное ВВ" value="GRANULIT" options={options} onChange={onChange} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("combobox", { name: "Основное ВВ" }));
    await user.type(screen.getByRole("searchbox"), "сфер");
    expect(screen.getAllByRole("option")).toHaveLength(1);
    await user.keyboard("{ArrowDown}{Enter}");
    expect(onChange).toHaveBeenCalledWith("SFERIT");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("показывает цену и единицу у каждой позиции", async () => {
    render(<CatalogSelect id="ex" label="Основное ВВ" value="" options={options} onChange={() => {}} />);
    await userEvent.click(screen.getByRole("combobox"));
    expect(screen.getByText("150,00 ₽/кг")).toBeInTheDocument();
  });

  it("Escape закрывает список и возвращает фокус кнопке", async () => {
    render(<CatalogSelect id="ex" label="Основное ВВ" value="" options={options} onChange={() => {}} />);
    const user = userEvent.setup();
    const button = screen.getByRole("combobox", { name: "Основное ВВ" });
    await user.click(button);
    expect(screen.getByRole("listbox")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(button).toHaveFocus();
  });
});
