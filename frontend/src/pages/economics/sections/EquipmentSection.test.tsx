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

  it("амортизация станка отображается в «Технике», даже если её раздел в модели — DRILLING, а не EQUIPMENT", () => {
    // `DRILL_DEPRECIATION`/`DRILL_INSURANCE` во фикстуре имеют `section: "DRILLING"`
    // (реальный раздел бэкенда, `cost/model/drilling.py`) — `groupOf` отправляет их
    // в раздел «Бурение», поэтому `group.lines` раздела «Техника» их не содержит.
    // `EquipmentSection` должен найти их сам, по всему расчёту (`economics.lines`),
    // а не только по строкам своего раздела.
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

    expect(screen.getByText("Амортизация станка")).toBeInTheDocument();
    expect(screen.getByText("Страхование станка")).toBeInTheDocument();
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
