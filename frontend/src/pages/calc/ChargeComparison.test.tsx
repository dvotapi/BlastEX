// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { BlastGeometryResponse } from "../../types";
import { defaultPanelInputs } from "./calcInputs";
import { ChargeComparison, type ComparisonVariant } from "./ChargeComparison";

afterEach(cleanup);

const EXPLOSIVES = [
  { key: "ПВВ Гранулит-РП", name: "Гранулит-РП" },
  { key: "ПЭВВ ЭВЕРСИН Э-100", name: "ЭВЕРСИН Э-100" },
];

function geometry(charge: string, nsi2 = false): BlastGeometryResponse {
  const hole_rows: [string, string][] = [
    ["Сетка a×b, м", "4.84 × 4.84"],
    ["Глубина, м", "11.0"],
    ["Заряд, кг", charge],
    ["Длина скважинного НСИ-1, м", "12"],
    ...(nsi2 ? ([["Длина скважинного НСИ-2, м", "6"]] as [string, string][]) : []),
    ["Замедление, мс", "500"],
  ];
  return {
    label: "Гранулит-РП",
    hole: { depth_m: 0 } as BlastGeometryResponse["hole"],
    block: { total_holes: 97 } as BlastGeometryResponse["block"],
    initiation: {} as BlastGeometryResponse["initiation"],
    hole_rows,
    block_rows: [
      ["Объём блока, м³", "22 000"],
      ["Масса ВВ на блок, кг", charge === "136" ? "13 174" : "17 359"],
    ],
  };
}

function variant(key: "left" | "right", overrides: Partial<ComparisonVariant> = {}): ComparisonVariant {
  return {
    key,
    label: key === "left" ? "Вариант 1" : "Вариант 2",
    shortLabel: key === "left" ? "Вар. 1" : "Вар. 2",
    color: key === "left" ? "#efe3c4" : "#d0483c",
    initialInputs: defaultPanelInputs(key === "left" ? EXPLOSIVES[0].key : EXPLOSIVES[1].key, 2.7),
    onInputsChange: vi.fn(),
    geometry: geometry(key === "left" ? "136" : "179"),
    error: "",
    ...overrides,
  };
}

function renderPanel(left = variant("left"), right = variant("right")) {
  render(
    <ChargeComparison
      cardKey="Карьер"
      variants={[left, right]}
      crownMm={152}
      gridLabel="4.84 × 4.84"
      depthM={11}
      explosives={EXPLOSIVES}
      nsiLengthOptions={[6, 12]}
      detonatorDelayOptions={[500, 700]}
      blockVolumeM3={22000}
      onBlockVolumeChange={vi.fn()}
      additionalHolesPct={3}
      onAdditionalHolesChange={vi.fn()}
    />,
  );
  return { left, right };
}

describe("ChargeComparison", () => {
  it("строит таблицы отличий по вариантам и один список общего", () => {
    renderPanel();
    expect(screen.getAllByRole("table").map((table) => table.querySelector("thead th")?.textContent)).toEqual(["Скважина", "Блок"]);
    const charge = screen.getByRole("rowheader", { name: "Заряд, кг" }).closest("tr")!;
    expect(within(charge).getAllByRole("cell").map((cell) => cell.textContent)).toEqual(["136", "179"]);
    expect(screen.getAllByRole("columnheader", { name: "Вар. 1" })).toHaveLength(2);
    const shared = screen.getByText("Общее для обоих").nextElementSibling as HTMLElement;
    expect(within(shared).getByText("Сетка a×b, м").nextElementSibling).toHaveTextContent("4.84 × 4.84");
    expect(within(shared).queryByText("Заряд, кг")).toBeNull();
    expect(screen.getByText(/97 скважин/)).toBeInTheDocument();
  });

  it("пока схема одного варианта не пришла, сравнения нет, а карточки уже есть", () => {
    renderPanel(variant("left"), variant("right", { geometry: null }));
    expect(screen.getByText("Считаем схемы заряда…")).toBeInTheDocument();
    expect(screen.getAllByRole("group")).toHaveLength(2);
  });

  it("второе поле длины НСИ появляется в карточке при двух НСИ на скважину", () => {
    renderPanel();
    const card = screen.getAllByRole("group")[0];
    expect(within(card).queryByLabelText("Длина НСИ-2, м")).toBeNull();
    fireEvent.change(within(card).getByLabelText("Скважинное НСИ"), { target: { value: "2" } });
    expect(within(card).getByLabelText("Длина НСИ-2, м")).toBeInTheDocument();
  });

  it("правка карточки уходит наверх", () => {
    const { right } = renderPanel();
    const card = screen.getAllByRole("group")[1];
    fireEvent.change(within(card).getByLabelText("Тип ВВ"), { target: { value: EXPLOSIVES[0].key } });
    expect(right.onInputsChange).toHaveBeenLastCalledWith(expect.objectContaining({ explosive_key: EXPLOSIVES[0].key }));
  });

  it("ошибку схемы варианта показывает рядом со сравнением", () => {
    renderPanel(variant("left", { error: "Сбой расчёта" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Вариант 1: Сбой расчёта");
  });
});
