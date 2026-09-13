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

    const headcount = screen.getByLabelText("Человек в смене: Мастер БВР");
    await user.clear(headcount);
    await user.type(headcount, "2");

    expect(onChange).toHaveBeenLastCalledWith({
      crew: params.crew.map((member, i) => (i === 0 ? { ...member, headcount: "2" } : member)),
    });
  });

  it("смены на блок видны подписью, а правятся из меню строки", async () => {
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

    // Значение видно всегда — поля в строке нет, оно не наезжает на суммы.
    expect(screen.getAllByText(/Смены на блок:/).length).toBeGreaterThan(0);
    expect(screen.queryByLabelText("Смен на блок: Мастер БВР")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Действия: Мастер БВР" }));
    await user.click(screen.getByRole("menuitem", { name: "Смены на блок" }));

    const shifts = screen.getByLabelText("Смен на блок: Мастер БВР");
    expect(shifts).toHaveFocus();
    await user.type(shifts, "3");

    expect(onChange).toHaveBeenLastCalledWith({
      crew: params.crew.map((member, i) => (i === 0 ? { ...member, shifts_per_block: "3" } : member)),
    });
  });

  it("показывает штат на ротацию экипажа техники из расчёта", () => {
    const { params, defaults, economics, group } = setup();
    const withRotation = {
      ...economics,
      natural: {
        ...economics.natural,
        values: { ...economics.natural.values, "crew_rotation.MASTER_BVR": "3" },
      },
    };
    render(
      <LaborSection
        group={group}
        params={params}
        defaults={defaults}
        economics={withRotation}
        volume={economics.block_volume_m3}
        canEdit
        onChange={vi.fn()}
      />,
    );

    expect(screen.getByText(/Штат на ротацию: 3 чел\./)).toBeInTheDocument();
    // У взрывника техники нет — и подписи нет.
    expect(screen.getAllByText(/Штат на ротацию/)).toHaveLength(1);
  });

  it("показывает «В смене» из расчёта, когда 0 в составе даёт одного человека", () => {
    const { params, defaults, economics, group } = setup();
    const zeroHeadcount = {
      ...params,
      crew: params.crew.map((member, i) => (i === 0 ? { ...member, headcount: 0 } : member)),
    };
    const withCrewPerShift = {
      ...economics,
      natural: {
        ...economics.natural,
        values: { ...economics.natural.values, "crew_per_shift.MASTER_BVR": "1" },
      },
    };
    render(
      <LaborSection
        group={group}
        params={zeroHeadcount}
        defaults={defaults}
        economics={withCrewPerShift}
        volume={economics.block_volume_m3}
        canEdit
        onChange={vi.fn()}
      />,
    );

    expect(screen.getByText(/В смене: 1 чел\./)).toBeInTheDocument();
  });

  it("не показывает «В смене», когда расчёт совпадает с составом", () => {
    const { params, defaults, economics, group } = setup();
    const withCrewPerShift = {
      ...economics,
      natural: {
        ...economics.natural,
        // У взрывника в составе уже 2 человека — расчёт подтверждает то же число.
        values: { ...economics.natural.values, "crew_per_shift.VZRYVNIK": "2" },
      },
    };
    render(
      <LaborSection
        group={group}
        params={params}
        defaults={defaults}
        economics={withCrewPerShift}
        volume={economics.block_volume_m3}
        canEdit
        onChange={vi.fn()}
      />,
    );

    expect(screen.queryByText(/В смене/)).not.toBeInTheDocument();
  });
});
