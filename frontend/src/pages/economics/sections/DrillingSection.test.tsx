// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DrillingSection } from "./DrillingSection";
import { buildEstimate } from "../estimateModel";
import { defaultsFixture, economicsFixture, paramsFixture } from "../testFixtures";
import type { ModelParameters } from "../../../types/blockEconomics";

afterEach(cleanup);

function setup(paramsPatch: Partial<ModelParameters> = {}) {
  const params = { ...paramsFixture(), ...paramsPatch };
  const defaults = defaultsFixture();
  const economics = economicsFixture();
  const group = buildEstimate(economics).find((g) => g.code === "DRILLING")!;
  return { params, defaults, economics, group };
}

describe("DrillingSection", () => {
  it("переключает режим и показывает источник ставки собственного бурения", async () => {
    const { params, defaults, economics, group } = setup();
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <DrillingSection
        group={group}
        params={params}
        defaults={defaults}
        economics={economics}
        volume={economics.block_volume_m3}
        canEdit
        onChange={onChange}
        onOpenDrillingPage={() => {}}
      />,
    );

    expect(screen.getByText("Расчёт бурения")).toHaveAttribute(
      "title",
      "drilling_conditions.COND_GRANITE (станок + порода)",
    );

    await user.click(screen.getByRole("radio", { name: "Субподряд" }));

    expect(onChange).toHaveBeenCalledWith({ drilling_executor: "SUBCONTRACTOR" });
  });

  it("выбор тарифа подрядчика ставит код и сбрасывает ручную ставку", async () => {
    const { params, defaults, economics, group } = setup({ drilling_executor: "SUBCONTRACTOR" });
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <DrillingSection
        group={group}
        params={params}
        defaults={defaults}
        economics={economics}
        volume={economics.block_volume_m3}
        canEdit
        onChange={onChange}
        onOpenDrillingPage={() => {}}
      />,
    );

    await user.click(screen.getByRole("combobox", { name: "Тариф" }));
    await user.click(screen.getByRole("option", { name: /DTH-бурение/ }));

    expect(onChange).toHaveBeenCalledWith({ subcontract_rate_code: "RATE_B", subcontract_rate_rub: null });
  });

  it("ручная ставка помечается «Ручной» и предлагает сохранить в справочник", async () => {
    const { params, defaults, economics, group } = setup({
      drilling_executor: "SUBCONTRACTOR",
      subcontract_rate_code: "RATE_B",
    });
    const onChange = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(
      <DrillingSection
        group={group}
        params={params}
        defaults={defaults}
        economics={economics}
        volume={economics.block_volume_m3}
        canEdit
        onChange={onChange}
        onOpenDrillingPage={() => {}}
      />,
    );

    const price = screen.getByLabelText("Ставка субподряда, ₽/м");
    await user.clear(price);
    await user.type(price, "185");

    expect(onChange).toHaveBeenLastCalledWith({ subcontract_rate_rub: "185" });

    rerender(
      <DrillingSection
        group={group}
        params={{ ...params, drilling_executor: "SUBCONTRACTOR", subcontract_rate_rub: "185" }}
        defaults={defaults}
        economics={economics}
        volume={economics.block_volume_m3}
        canEdit
        onChange={onChange}
        onOpenDrillingPage={() => {}}
      />,
    );

    expect(screen.getByRole("button", { name: "Сохранить тариф в справочник" })).toBeEnabled();
  });

  it("без выбранного подрядчика (пустой справочник контрагентов) кнопка сохранения тарифа недоступна", () => {
    const { params, economics, group } = setup({
      drilling_executor: "SUBCONTRACTOR",
      subcontract_rate_rub: "185",
    });
    const defaults = { ...defaultsFixture(), counterparties: [] };
    const onChange = vi.fn();
    render(
      <DrillingSection
        group={group}
        params={params}
        defaults={defaults}
        economics={economics}
        volume={economics.block_volume_m3}
        canEdit
        onChange={onChange}
        onOpenDrillingPage={() => {}}
      />,
    );

    const button = screen.getByRole("button", { name: "Сохранить тариф в справочник" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("title", "Сначала выберите подрядчика");
  });

  it("после выбора подрядчика кнопка сохранения тарифа доступна", async () => {
    const { params, economics, group } = setup({ drilling_executor: "SUBCONTRACTOR" });
    const defaults = {
      ...defaultsFixture(),
      counterparties: [
        { code: "CONTR_A", name: "ООО «Буровик»" },
        { code: "CONTR_B", name: "ООО «Скважина»" },
      ],
    };
    const onChange = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(
      <DrillingSection
        group={group}
        params={params}
        defaults={defaults}
        economics={economics}
        volume={economics.block_volume_m3}
        canEdit
        onChange={onChange}
        onOpenDrillingPage={() => {}}
      />,
    );

    await user.click(screen.getByRole("combobox", { name: "Подрядчик" }));
    await user.click(screen.getByRole("option", { name: "ООО «Скважина»" }));

    const price = screen.getByLabelText("Ставка субподряда, ₽/м");
    await user.clear(price);
    await user.type(price, "185");

    rerender(
      <DrillingSection
        group={group}
        params={{ ...params, subcontract_rate_rub: "185" }}
        defaults={defaults}
        economics={economics}
        volume={economics.block_volume_m3}
        canEdit
        onChange={onChange}
        onOpenDrillingPage={() => {}}
      />,
    );

    expect(screen.getByRole("button", { name: "Сохранить тариф в справочник" })).toBeEnabled();
  });
});
