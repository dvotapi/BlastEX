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

  it("список не обрезается предком: он рисуется порталом в body, а не внутри строки", async () => {
    // Ячейка названия в смете обрезает содержимое по многоточию — список,
    // нарисованный внутри неё, был бы срезан по высоте строки.
    render(
      <div style={{ overflow: "hidden", height: 20 }}>
        <CatalogSelect id="ex" label="Основное ВВ" value="" options={options} onChange={() => {}} />
      </div>,
    );
    await userEvent.click(screen.getByRole("combobox", { name: "Основное ВВ" }));

    const listbox = screen.getByRole("listbox");
    expect(listbox.closest(".catalog-select")).toBeNull();
    expect(listbox.closest(".catalog-select-popover")?.parentElement).toBe(document.body);
  });

  it("клик по пункту списка выбирает позицию, а не считается кликом вне", async () => {
    // Поповер живёт в портале и предком кнопки не является: без проверки
    // самого поповера обработчик «клик вне» закрывал список раньше выбора.
    const onChange = vi.fn();
    render(<CatalogSelect id="ex" label="Основное ВВ" value="" options={options} onChange={onChange} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("combobox", { name: "Основное ВВ" }));
    await user.click(screen.getByRole("option", { name: /Березит/ }));

    expect(onChange).toHaveBeenCalledWith("BEREZIT");
  });

  it("клик мимо комбобокса закрывает список", async () => {
    render(<CatalogSelect id="ex" label="Основное ВВ" value="" options={options} onChange={() => {}} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("combobox", { name: "Основное ВВ" }));
    expect(screen.getByRole("listbox")).toBeInTheDocument();

    await user.click(document.body);

    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("в строке сметы кнопка выглядит текстом, в форме — полем", () => {
    const { rerender } = render(
      <CatalogSelect id="ex" label="Основное ВВ" value="GRANULIT" options={options} onChange={() => {}} />,
    );
    expect(screen.getByRole("combobox", { name: "Основное ВВ" })).toHaveClass("is-ghost");

    rerender(
      <CatalogSelect
        id="ex"
        label="Основное ВВ"
        value="GRANULIT"
        options={options}
        onChange={() => {}}
        variant="field"
      />,
    );
    expect(screen.getByRole("combobox", { name: "Основное ВВ" })).toHaveClass("is-field");
  });
});
