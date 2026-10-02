// @vitest-environment jsdom
// Таблица скважин (TASK-013, PR 3, ревью Codex #104): правка глубины и забоя
// помечает длину «вручную», как карточка скважины, — иначе автопересчёт по
// кровле затирал введённую длину. Угол и азимут пересчёт сохраняет сам.
import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { emptyHoleGeology, type Hole } from "../../types/design";
import { HoleTable } from "./HoleTable";

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

function renderTable(value: Hole) {
  const onUpdateHole = vi.fn();
  const { container } = render(
    <HoleTable
      holes={[value]}
      selected={new Set()}
      onSelectedChange={vi.fn()}
      onUpdateHole={onUpdateHole}
      onDeleteSelected={vi.fn()}
      insertKind="production"
      onInsertKindChange={vi.fn()}
      onSetEnabled={vi.fn()}
    />,
  );
  // Колонки: X, Y, Z забоя, глубина, угол, азимут, Ø, перебур.
  const [toeX, toeY, toeZ, depth, angle] = Array.from(container.querySelectorAll<HTMLInputElement>("tbody input[type=number]"));
  return { onUpdateHole, toeX, toeY, toeZ, depth, angle };
}

describe("HoleTable: ручная длина", () => {
  it("глубина правится и помечается «вручную», прежние пометки сохраняются", () => {
    const { onUpdateHole, depth } = renderTable(hole({ manual: ["collar_z"] }));

    fireEvent.change(depth, { target: { value: "9" } });

    const [, patch] = onUpdateHole.mock.calls[0];
    expect(patch.toe.z).toBeCloseTo(411);
    expect(patch.manual).toEqual(["collar_z", "length"]);
  });

  it.each([
    ["X", "toeX", "11"],
    ["Y", "toeY", "6"],
    ["Z", "toeZ", "408"],
  ] as const)("координата %s забоя помечает длину «вручную»", (_axis, field, value) => {
    const rendered = renderTable(hole());

    fireEvent.change(rendered[field], { target: { value } });

    expect(rendered.onUpdateHole.mock.calls[0][1].manual).toEqual(["length"]);
  });

  it("угол не делает длину ручной", () => {
    const { onUpdateHole, angle } = renderTable(hole());

    fireEvent.change(angle, { target: { value: "10" } });

    expect(onUpdateHole.mock.calls[0][1].manual).toBeUndefined();
  });
});
