// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { CadImportHelp } from "./CadImportHelp";
import { CAD_META } from "./testing/fixtures";

afterEach(cleanup);

beforeAll(() => {
  HTMLDialogElement.prototype.showModal = vi.fn(function (this: HTMLDialogElement) {
    this.open = true;
  });
  HTMLDialogElement.prototype.close = vi.fn(function (this: HTMLDialogElement) {
    this.open = false;
  });
});

describe("CadImportHelp", () => {
  it("кнопка «?» открывает справку с разделом «Слои и роли»", () => {
    render(<CadImportHelp meta={CAD_META} />);

    fireEvent.click(screen.getByRole("button", { name: "Справка по импорту чертежа" }));

    const dialog = screen.getByRole("dialog", { name: "Импорт чертежа: справка" });
    expect((dialog as HTMLDialogElement).open).toBe(true);
    expect(within(dialog).getByRole("heading", { name: "Слои и роли" })).toBeTruthy();
    expect(within(dialog).getByRole("heading", { name: "Что присылает маркшейдер" })).toBeTruthy();
    expect(within(dialog).getByRole("heading", { name: "Шаблон слоёв объекта" })).toBeTruthy();
  });

  it("перечисляет все роли из каталога сервера с пояснением", () => {
    render(<CadImportHelp meta={CAD_META} />);
    fireEvent.click(screen.getByRole("button", { name: "Справка по импорту чертежа" }));

    const roles = within(screen.getByRole("list", { name: "Роли слоёв" })).getAllByRole("listitem");
    expect(roles.map((item) => item.querySelector("b")?.textContent)).toEqual([
      "Контур блока.",
      "Проектная линия.",
      "Бровка верхняя.",
      "Бровка нижняя.",
      "Характерная линия.",
      "Горизонталь.",
      "Отметки поверхности.",
      "Ситуация.",
      "Не использовать.",
      "Бровки (по Z).",
    ]);
    expect(roles.every((item) => (item.textContent ?? "").length > 30)).toBe(true);
  });

  it("объясняет бейджи происхождения", () => {
    render(<CadImportHelp meta={CAD_META} />);
    fireEvent.click(screen.getByRole("button", { name: "Справка по импорту чертежа" }));

    const badges = within(screen.getByRole("list", { name: "Бейджи происхождения" })).getAllByRole("listitem");
    expect(badges.map((item) => item.querySelector("b")?.textContent)).toEqual(["шаблон.", "авто.", "по Z.", "вручную."]);
  });
});

describe("CadImportHelp: контур блока (PR 2)", () => {
  it("описывает четыре способа, два контура и замыкающий отрезок", () => {
    render(<CadImportHelp meta={CAD_META} />);
    fireEvent.click(screen.getByRole("button", { name: "Справка по импорту чертежа" }));
    const dialog = screen.getByRole("dialog", { name: "Импорт чертежа: справка" });

    expect(within(dialog).getByRole("heading", { name: "Контур блока" })).toBeTruthy();
    const methods = within(within(dialog).getByRole("list", { name: "Способы контура" })).getAllByRole("listitem");
    expect(methods.map((item) => item.querySelector("b")?.textContent)).toEqual([
      "Готовый.",
      "Щелчок внутри.",
      "Сборка.",
      "Блок по бровке.",
    ]);
    expect(within(dialog).getByRole("heading", { name: "Два контура и площади" })).toBeTruthy();
    expect(dialog.textContent).toContain("Замыкающий отрезок");
    expect(dialog.textContent).toContain("свободная поверхность");
    // Старого построения «полосой между линиями» в справке больше нет.
    expect(dialog.textContent).not.toContain("полосой между");
    // Область «Щелчка внутри» дробят лишние линии — справка подсказывает, что делать.
    expect(dialog.textContent).toContain("снимите их роль");
    expect(dialog.textContent).not.toContain("блок 66 вар 2");
    // Какую площадь маркшейдер называет площадью блока — выбор на объекте.
    expect(dialog.textContent).toContain("«Площадь блока»");
    expect(dialog.textContent).toContain("хранится на объекте работ");
  });
});
