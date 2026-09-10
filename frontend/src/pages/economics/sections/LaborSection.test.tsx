// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LaborSection } from "./LaborSection";
import { buildEstimate } from "../estimateModel";
import { defaultsFixture, economicsFixture, paramsFixture } from "../testFixtures";

afterEach(cleanup);

function setup() {
  const params = paramsFixture();
  const defaults = defaultsFixture();
  const economics = economicsFixture();
  const group = buildEstimate(economics).find((g) => g.code === "LABOR")!;
  return { params, defaults, economics, group };
}

describe("LaborSection", () => {
  it("добавляет должность первой незанятой из прямых", async () => {
    const { params, defaults, economics, group } = setup();
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <LaborSection
        group={group}
        params={params}
        defaults={defaults}
        economics={economics}
        volume={economics.block_volume_m3}
        canEdit
        onChange={onChange}
      />,
    );

    await user.click(screen.getByRole("button", { name: "+ Добавить должность" }));

    expect(onChange).toHaveBeenCalledWith({
      crew: [...params.crew, { position_code: "MASHINIST_SZM", headcount: 1, shifts_per_block: null }],
    });
  });

  it("изменение должности вызывает onChange с новым кодом", async () => {
    const { params, defaults, economics, group } = setup();
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <LaborSection
        group={group}
        params={params}
        defaults={defaults}
        economics={economics}
        volume={economics.block_volume_m3}
        canEdit
        onChange={onChange}
      />,
    );

    await user.click(screen.getAllByRole("combobox", { name: "Должность" })[0]);
    await user.click(screen.getByRole("option", { name: /Взрывник/ }));

    expect(onChange).toHaveBeenCalledWith({
      crew: params.crew.map((member, i) => (i === 0 ? { ...member, position_code: "VZRYVNIK" } : member)),
    });
  });

  it("норматив становится ручным после правки численности", async () => {
    const { params, defaults, economics, group } = setup();
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <LaborSection
        group={group}
        params={params}
        defaults={defaults}
        economics={economics}
        volume={economics.block_volume_m3}
        canEdit
        onChange={onChange}
      />,
    );

    // Состав бригады совпадает с шаблоном пакета — обе записи стартуют с «Норматив».
    expect(screen.getAllByText("Норматив").length).toBeGreaterThan(0);

    const headcount = screen.getByLabelText("Численность: Мастер БВР");
    await user.clear(headcount);
    await user.type(headcount, "2");

    expect(onChange).toHaveBeenLastCalledWith({
      crew: params.crew.map((member, i) => (i === 0 ? { ...member, headcount: "2" } : member)),
    });
  });
});
