// @vitest-environment jsdom
// Инспектор скважины (TASK-013, PR 3): отметка устья и длина правятся руками
// и помечаются «вручную» — пересчёт по кровле их не затирает; «Вернуть
// расчётное» снимает пометку. Флаги кровли видны.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { emptyHoleGeology, type Hole } from "../../types/design";
import { HoleInspector } from "./HoleInspector";

afterEach(cleanup);

function hole(extra: Partial<Hole> = {}): Hole {
  return {
    id: "1-01",
    row: 0,
    col: 0,
    collar: { x: 10, y: 5, z: 420 },
    toe: { x: 10, y: 5, z: 409 },
    diameter_mm: 152,
    subdrill_m: 1,
    kind: "production",
    source: "generated",
    enabled: true,
    ...emptyHoleGeology(),
    ...extra,
  };
}

function renderInspector(value: Hole, flags: string[] = []) {
  const onUpdateHole = vi.fn();
  render(
    <HoleInspector
      hole={value}
      flags={flags as never}
      onClose={vi.fn()}
      onUpdateHole={onUpdateHole}
      onSetEnabled={vi.fn()}
      onDelete={vi.fn()}
    />,
  );
  return onUpdateHole;
}

describe("HoleInspector: ручная правка", () => {
  it("Z устья правится — скважина сдвигается по вертикали и помечается «вручную»", () => {
    const onUpdateHole = renderInspector(hole());

    fireEvent.change(screen.getByLabelText(/Z устья/), { target: { value: "421" } });

    const [, patch] = onUpdateHole.mock.calls[0];
    expect(patch.collar).toEqual({ x: 10, y: 5, z: 421 });
    expect(patch.toe.z).toBeCloseTo(410);
    expect(patch.manual).toEqual(["collar_z"]);
  });

  it("длина правится и помечается «вручную»", () => {
    const onUpdateHole = renderInspector(hole({ manual: ["collar_z"] }));

    fireEvent.change(screen.getByLabelText(/Глубина/), { target: { value: "9" } });

    const [, patch] = onUpdateHole.mock.calls[0];
    expect(patch.toe.z).toBeCloseTo(411);
    expect(patch.manual).toEqual(["collar_z", "length"]);
  });

  it("правка забоя — тоже ручная длина", () => {
    const onUpdateHole = renderInspector(hole());

    fireEvent.change(screen.getByLabelText("Забой Z"), { target: { value: "408" } });

    expect(onUpdateHole.mock.calls[0][1].manual).toEqual(["length"]);
  });

  it("«Вернуть расчётное» снимает пометку; без пометки кнопки нет", () => {
    const onUpdateHole = renderInspector(hole({ manual: ["collar_z", "length"] }));

    expect(screen.getAllByText("вручную")).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: "Вернуть расчётное" }));
    expect(onUpdateHole).toHaveBeenCalledWith("1-01", { manual: [] });

    cleanup();
    renderInspector(hole());
    expect(screen.queryByRole("button", { name: "Вернуть расчётное" })).toBeNull();
  });

  it("флаги кровли видны", () => {
    renderInspector(hole(), ["outside_surface", "short_bench"]);

    expect(screen.getByText(/вне поверхности/)).toBeTruthy();
    expect(screen.getByText(/H < 1 м/)).toBeTruthy();
  });
});
