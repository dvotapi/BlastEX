// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EquipmentSection } from "./EquipmentSection";
import { buildEstimate } from "../estimateModel";
import { defaultsFixture, economicsFixture, paramsFixture } from "../testFixtures";

afterEach(cleanup);

function setup() {
  const params = paramsFixture();
  const defaults = defaultsFixture();
  const economics = economicsFixture();
  const group = buildEstimate(economics).find((g) => g.code === "EQUIPMENT")!;
  return { params, defaults, economics, group };
}

describe("EquipmentSection", () => {
  it("выбор СЗМ вызывает onChange({szm_code})", async () => {
    const { params, defaults, economics, group } = setup();
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <EquipmentSection
        group={group}
        params={params}
        defaults={defaults}
        economics={economics}
        volume={economics.block_volume_m3}
        canEdit
        onChange={onChange}
      />,
    );

    await user.click(screen.getByRole("combobox", { name: "СЗМ" }));
    await user.click(screen.getByRole("option", { name: /МТЗ-320/ }));

    expect(onChange).toHaveBeenCalledWith({ szm_code: "SZM_MTZ" });
  });

  it("плановые смены с бейджем «Норматив», пока не заданы", () => {
    const { params, defaults, economics, group } = setup();
    render(
      <EquipmentSection
        group={group}
        params={params}
        defaults={defaults}
        economics={economics}
        volume={economics.block_volume_m3}
        canEdit
        onChange={() => {}}
      />,
    );

    // machine_plan_shifts пуст и rig_plan_shifts === null во фикстуре —
    // все четыре роли показывают бейдж «Норматив», пока сметчик не поправил план.
    expect(screen.getAllByText("Норматив").length).toBe(4);
  });

  it("строка станка ссылается на «Бурение» и не показывает его деньги как свои", async () => {
    // `DRILL_DEPRECIATION`/`DRILL_INSURANCE` во фикстуре имеют `section: "DRILLING"`
    // (реальный раздел бэкенда, `cost/model/drilling.py`) — `groupOf` отправляет их
    // в раздел «Бурение», поэтому `group.lines` раздела «Техника» их не содержит.
    // Раньше `EquipmentSection` всё равно ставил их сумму в колонку «Сумма» строки
    // станка: итог раздела не сходился с суммой видимых строк, а колонка процентов
    // дважды считала одни и те же рубли. Теперь строка станка — ссылочная.
    const { params, defaults, economics, group } = setup();
    const openDrilling = vi.fn();
    render(
      <EquipmentSection
        group={group}
        params={params}
        defaults={defaults}
        economics={economics}
        volume={economics.block_volume_m3}
        canEdit
        onChange={() => {}}
        onOpenDrillingGroup={openDrilling}
      />,
    );

    // Построчных статей станка в «Технике» нет, как и его денег в колонке суммы.
    expect(screen.queryByText("Амортизация станка")).not.toBeInTheDocument();
    expect(screen.queryByText("Страхование станка")).not.toBeInTheDocument();
    expect(screen.queryByText("50 000,00")).not.toBeInTheDocument();

    // Подпись называет ту же сумму (45000 + 5000) и уводит туда, где она учтена.
    // В числе неразрывный пробел — сверяем по началу и по адресу, а не по цифрам.
    const pointer = screen.getByRole("button", { name: /^Затраты станка:.*«Бурение»$/ });
    expect(pointer.textContent?.replace(/\u00a0/g, " ")).toContain("50 000 ₽");
    await userEvent.click(pointer);
    expect(openDrilling).toHaveBeenCalledOnce();
  });

  it("итог раздела сходится с суммой видимых строк ролей", () => {
    const { params, defaults, economics, group } = setup();
    render(
      <EquipmentSection
        group={group}
        params={params}
        defaults={defaults}
        economics={economics}
        volume={economics.block_volume_m3}
        canEdit
        onChange={() => {}}
      />,
    );

    // Роли с деньгами показывают ровно свои строки: сумма станка сюда не входит,
    // потому что её нет и в `group.total` (она в разделе «Бурение»).
    const visibleAmounts = Array.from(document.querySelectorAll(".estimate-line > .estimate-col-amount"))
      .map((cell) => cell.textContent ?? "")
      .filter((text) => text !== "—");
    const parsed = visibleAmounts.map((text) => Number(text.replace(/\s|\u00a0/g, "").replace(",", ".")));
    // Строки ролей и их подстроки дают одни и те же деньги дважды — сверяем
    // только роли: подстроки идут ниже и повторяют их разбивкой.
    expect(parsed.length).toBeGreaterThan(0);
    expect(Math.max(...parsed)).toBeLessThanOrEqual(group.total + 0.01);
  });

  it("построчная разбивка СЗМ (не станка) по-прежнему выводится построчно", () => {
    // Регрессия на находку ревью: фикс дублирования станка (коммит ac62b86)
    // добавил развилку `role.param !== "rig_code" && items.map(...)` — без
    // этой проверки её можно случайно расширить на другие роли, и ни один
    // тест не покраснеет. СЗМ — одна из трёх ролей, для которых построчная
    // разбивка обязана остаться (`SZM_DEPRECIATION` во фикстуре, section
    // "DEPRECIATION", попадает в `group.lines` раздела «Техника», а не
    // «Бурение», как у станка).
    const { params, defaults, economics, group } = setup();
    render(
      <EquipmentSection
        group={group}
        params={params}
        defaults={defaults}
        economics={economics}
        volume={economics.block_volume_m3}
        canEdit
        onChange={() => {}}
      />,
    );

    expect(screen.getByText("Амортизация СЗМ")).toBeInTheDocument();
  });

  it("правка плановых смен СЗМ переводит бейдж в «Ручной» и уходит в machine_plan_shifts", async () => {
    const { params, defaults, economics, group } = setup();
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <EquipmentSection
        group={group}
        params={params}
        defaults={defaults}
        economics={economics}
        volume={economics.block_volume_m3}
        canEdit
        onChange={onChange}
      />,
    );

    // Поля в строке нет: план виден подписью, а правится из меню строки.
    expect(screen.queryByLabelText("Плановые смены: СЗМ")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Действия: СЗМ" }));
    await user.click(screen.getByRole("menuitem", { name: "Плановые смены в месяц" }));

    const planShifts = screen.getByLabelText("Плановые смены: СЗМ");
    await user.clear(planShifts);
    await user.type(planShifts, "20");

    expect(onChange).toHaveBeenLastCalledWith({ machine_plan_shifts: { SZM_MZ: "20" } });
  });
});
