// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ExplosivesSection } from "./ExplosivesSection";
import { buildEstimate } from "../estimateModel";
import { defaultsFixture, economicsFixture, paramsFixture } from "../testFixtures";

afterEach(cleanup);

function setup() {
  const params = paramsFixture();
  const defaults = defaultsFixture();
  const economics = economicsFixture();
  const group = buildEstimate(economics).find((g) => g.code === "EXPLOSIVES")!;
  return { params, defaults, economics, group };
}

describe("ExplosivesSection", () => {
  it("смена номенклатуры вызывает onChange с новым кодом роли", async () => {
    const { params, defaults, economics, group } = setup();
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <ExplosivesSection
        group={group}
        params={params}
        defaults={defaults}
        economics={economics}
        volume={economics.block_volume_m3}
        canEdit
        onChange={onChange}
      />,
    );

    await user.click(screen.getByRole("combobox", { name: "Основное ВВ" }));
    await user.click(screen.getByRole("option", { name: /Сферит ДТ/ }));

    expect(onChange).toHaveBeenCalledWith({ nomenclature: { ...params.nomenclature, EXPLOSIVE: "SFERIT" } });
  });

  it("прячет роль без позиции в паспорте и предлагает добавить её вручную", async () => {
    const { params, defaults, economics, group } = setup();
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <ExplosivesSection
        group={group}
        params={params}
        defaults={defaults}
        economics={economics}
        volume={economics.block_volume_m3}
        canEdit
        onChange={onChange}
      />,
    );

    expect(screen.queryByRole("combobox", { name: "Стартовые НСИ" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "+ Добавить материал" }));
    await user.click(screen.getByRole("menuitem", { name: "Стартовые НСИ" }));

    expect(screen.getByRole("combobox", { name: "Стартовые НСИ" })).toBeInTheDocument();
  });

  it("«Убрать» очищает выбор роли номенклатуры", async () => {
    const { params, defaults, economics, group } = setup();
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <ExplosivesSection
        group={group}
        params={params}
        defaults={defaults}
        economics={economics}
        volume={economics.block_volume_m3}
        canEdit
        onChange={onChange}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Действия: Основное ВВ" }));
    await user.click(screen.getByRole("menuitem", { name: "Убрать" }));

    expect(onChange).toHaveBeenCalledWith({ nomenclature: { ...params.nomenclature, EXPLOSIVE: "" } });
  });

  it("количество электродетонаторов правится вручную и помечено «Ручной»", async () => {
    const { params, defaults, economics, group } = setup();
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <ExplosivesSection
        group={group}
        params={params}
        defaults={defaults}
        economics={economics}
        volume={economics.block_volume_m3}
        canEdit
        onChange={onChange}
      />,
    );

    const qty = screen.getByLabelText("Количество: Электродетонаторы");
    await user.clear(qty);
    await user.type(qty, "30");

    expect(onChange).toHaveBeenLastCalledWith({ electric_detonators_qty: "30" });
  });
});
