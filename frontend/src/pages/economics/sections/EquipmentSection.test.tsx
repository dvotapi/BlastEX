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

  it("сумма амортизации станка учтена в «Технике», но построчно не дублируется — она уже в «Бурении»", () => {
    // `DRILL_DEPRECIATION`/`DRILL_INSURANCE` во фикстуре имеют `section: "DRILLING"`
    // (реальный раздел бэкенда, `cost/model/drilling.py`) — `groupOf` отправляет их
    // в раздел «Бурение», поэтому `group.lines` раздела «Техника» их не содержит.
    // `EquipmentSection` находит их сам, по всему расчёту (`economics.lines`), и
    // складывает в сумму строки роли «Буровая установка», но НЕ выводит построчно —
    // построчная разбивка уже есть в разделе «Бурение» (`OwnDrillingEditor`), и
    // повторный построчный вывод в «Технике» вводил сметчика в заблуждение
    // (одна и та же сумма амортизации на двух страницах).
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

    // Построчных статей станка в «Технике» больше нет.
    expect(screen.queryByText("Амортизация станка")).not.toBeInTheDocument();
    expect(screen.queryByText("Страхование станка")).not.toBeInTheDocument();
    // Сноска поясняет, где искать разбивку, и называет ту же сумму: 45000 + 5000 = 50000,00.
    expect(screen.getByText(/Построчная разбивка.*станка.*«Бурение»/)).toBeInTheDocument();
    // Сумма строки роли «Буровая установка» — не нулевая: 45000 + 5000 = 50000,00.
    expect(screen.getByText("50 000,00")).toBeInTheDocument();
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

    const planShifts = screen.getByLabelText("Плановые смены: СЗМ");
    await user.clear(planShifts);
    await user.type(planShifts, "20");

    expect(onChange).toHaveBeenLastCalledWith({ machine_plan_shifts: { SZM_MZ: "20" } });
  });
});
