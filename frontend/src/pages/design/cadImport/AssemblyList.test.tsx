// @vitest-environment jsdom
// Список участков сборки: слой, длина, разрыв до следующего, «развёрнут».
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CadItemInfo } from "../../../types/cad";
import type { CadContourItem } from "../../../types/design";
import { AssemblyList } from "./AssemblyList";

afterEach(cleanup);

const ITEMS: CadContourItem[] = [
  { kind: "part", handle: "6C3", start_m: 0, end_m: 134.3, points: [], flip: false, label: "" },
  { kind: "segment", handle: "", start_m: 0, end_m: 0, points: [[0, 0], [1, 1]], flip: false, label: "" },
  { kind: "polyline", handle: "", start_m: 0, end_m: 0, points: [[0, 0], [1, 1]], flip: false, label: "Тыл" },
];
const INFO: CadItemInfo[] = [
  { kind: "part", handle: "6C3", layer: "Горизонт +410", length_m: 134.3, reversed: true, gap_to_next_m: 0.2, link: "joined" },
  { kind: "segment", handle: "", layer: "", length_m: 1.41, reversed: false, gap_to_next_m: 2.75, link: "closing" },
  { kind: "polyline", handle: "", layer: "", length_m: 1.41, reversed: false, gap_to_next_m: 0, link: "joined" },
];

describe("AssemblyList", () => {
  it("показывает участки по порядку с разрывами и разворотом", () => {
    render(<AssemblyList items={ITEMS} info={INFO} selected={null} onSelect={vi.fn()} />);

    const rows = screen.getAllByRole("row").slice(1);
    expect(rows).toHaveLength(3);
    expect(rows[0].textContent).toContain("Горизонт +410 · 6C3");
    expect(rows[0].textContent).toContain("134,3 м");
    expect(rows[0].textContent).toContain("развёрнут");
    expect(rows[0].textContent).toContain("стык 0,20 м");
    expect(rows[1].textContent).toContain("Отрезок");
    expect(rows[1].textContent).toContain("замыкающий 2,75 м");
    expect(rows[2].textContent).toContain("Тыл");
  });

  it("щелчок по строке выбирает участок", () => {
    const onSelect = vi.fn();
    render(<AssemblyList items={ITEMS} info={INFO} selected={1} onSelect={onSelect} />);

    expect(screen.getAllByRole("row")[2].classList.contains("is-selected")).toBe(true);
    fireEvent.click(screen.getAllByRole("row")[1]);
    expect(onSelect).toHaveBeenCalledWith(0);
  });

  it("без ответа сервера — длины нет, участки всё равно видны", () => {
    render(<AssemblyList items={ITEMS.slice(0, 1)} info={[]} selected={null} onSelect={vi.fn()} />);
    expect(screen.getAllByRole("row")[1].textContent).toContain("6C3");
  });
});
