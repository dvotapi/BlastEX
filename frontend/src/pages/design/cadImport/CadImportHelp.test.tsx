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

describe("CadImportHelp: поверхность и длины скважин (PR 3)", () => {
  function open() {
    render(<CadImportHelp meta={CAD_META} />);
    fireEvent.click(screen.getByRole("button", { name: "Справка по импорту чертежа" }));
    return screen.getByRole("dialog", { name: "Импорт чертежа: справка" });
  }

  it("роли линий в кровле и почему бровка — ограничитель", () => {
    const dialog = open();

    expect(within(dialog).getByRole("heading", { name: "Поверхность и длины скважин" })).toBeTruthy();
    const roles = within(within(dialog).getByRole("list", { name: "Линии в кровле" })).getAllByRole("listitem");
    expect(roles.map((item) => item.querySelector("b")?.textContent)).toEqual([
      "Бровки.",
      "Характерные линии.",
      "Горизонтали.",
      "Отметки поверхности.",
      "Граница.",
    ]);
    expect(dialog.textContent).toContain("Почему бровка — ограничитель");
    expect(dialog.textContent).toContain("первый ряд");
    expect(dialog.textContent).toContain("выброс");
  });

  it("формула длины, ручная правка, флаги и объёмы", () => {
    const dialog = open();

    expect(dialog.textContent).toContain("L = (S − Z) / cos α + Δ");
    expect(dialog.textContent).toContain("вдоль оси");
    expect(dialog.textContent).toContain("«Вернуть расчётное»");
    expect(dialog.textContent).toContain("вне поверхности");
    expect(dialog.textContent).toContain("H < 1 м");
    expect(within(dialog).getByRole("heading", { name: "Итог и объёмы" })).toBeTruthy();
    expect(dialog.textContent).toContain("по нижней бровке");
    expect(dialog.textContent).toContain("S ср × H");
    expect(dialog.textContent).toContain("Подтверждаю высоту уступа");
  });

  it("«Построить блок» ставит кровлю и снимает поверхность подошвы", () => {
    const dialog = open();

    expect(dialog.textContent).toContain("поверхность подошвы снимается");
    expect(dialog.textContent).not.toContain("Поверхности паспорта построение не меняет");
  });
});

describe("CadImportHelp: ситуация и система координат (PR 4)", () => {
  function openHelp() {
    render(<CadImportHelp meta={CAD_META} />);
    fireEvent.click(screen.getByRole("button", { name: "Справка по импорту чертежа" }));
    return screen.getByRole("dialog", { name: "Импорт чертежа: справка" });
  }

  it("источник, серии и версии, что видно в других паспортах", () => {
    const dialog = openHelp();

    expect(within(dialog).getByRole("heading", { name: "Ситуация и система координат" })).toBeTruthy();
    expect(dialog.textContent).toContain("Название и дата съёмки");
    expect(dialog.textContent).toContain("серии");
    expect(dialog.textContent).toContain("самую свежую версию");
    expect(dialog.textContent).toContain("в других паспортах объекта");
    expect(dialog.textContent).toContain("«Вид»");
  });

  it("виды объектов ситуации — из каталога сервера", () => {
    const dialog = openHelp();

    const kinds = within(within(dialog).getByRole("list", { name: "Виды объектов ситуации" })).getAllByRole("listitem");
    expect(kinds.map((item) => item.textContent)).toEqual(["Контур карьера", "Дорога", "ЛЭП", "Склад", "Здание", "Прочее"]);
  });

  it("СК объекта, предупреждение 5 км, повторный файл и удаление", () => {
    const dialog = openHelp();

    expect(dialog.textContent).toContain("МСК-66 зона 1");
    expect(dialog.textContent).toContain("дальше 5 км");
    expect(dialog.textContent).toContain("не пересчитываются");
    expect(dialog.textContent).toContain("открывает прежний разбор");
    expect(dialog.textContent).toContain("«Чертежи объекта»");
    expect(dialog.textContent).toContain("насовсем");
    // Блок 66 в справке — частный пример заказчика; нужен общий (известная проблема PR 2).
    expect(dialog.textContent).not.toContain("блока 66");
  });
});
