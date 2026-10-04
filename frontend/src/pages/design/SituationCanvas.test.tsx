// @vitest-environment jsdom
// Подложка ситуации под SVG плана (TASK-013, PR 4): холст рисует штрихи
// слоёв; перерисовка — только при смене штрихов или размера.
import { cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SituationCanvas } from "./SituationCanvas";
import type { SituationStroke } from "./situationLayer";

type Ctx = Record<string, ReturnType<typeof vi.fn> | unknown>;
let ctx: Ctx;

beforeEach(() => {
  ctx = {
    setTransform: vi.fn(),
    clearRect: vi.fn(),
    beginPath: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    stroke: vi.fn(),
    fillRect: vi.fn(),
    strokeStyle: "",
    fillStyle: "",
    lineWidth: 0,
  };
  HTMLCanvasElement.prototype.getContext = vi.fn(() => ctx) as unknown as HTMLCanvasElement["getContext"];
});
afterEach(cleanup);

const STROKES: SituationStroke[] = [
  { key: "a", color: "#ff0000", polylines: [[0, 0, 10, 0, 10, 10]], points: [] },
  { key: "b", color: "#3a4540", polylines: [], points: [5, 5, 6, 6] },
];

describe("SituationCanvas", () => {
  it("рисует по штриху на слой и точки квадратиками", () => {
    render(<SituationCanvas strokes={STROKES} width={400} height={300} />);

    expect(ctx.clearRect).toHaveBeenCalledTimes(1);
    expect(ctx.moveTo).toHaveBeenCalledWith(0, 0);
    expect(ctx.lineTo).toHaveBeenCalledWith(10, 10);
    expect(ctx.stroke).toHaveBeenCalledTimes(1);
    expect(ctx.fillRect).toHaveBeenCalledTimes(2);
  });

  it("те же штрихи — без перерисовки", () => {
    const { rerender } = render(<SituationCanvas strokes={STROKES} width={400} height={300} />);
    rerender(<SituationCanvas strokes={STROKES} width={400} height={300} />);
    expect(ctx.clearRect).toHaveBeenCalledTimes(1);

    rerender(<SituationCanvas strokes={[...STROKES]} width={400} height={300} />);
    expect(ctx.clearRect).toHaveBeenCalledTimes(2);
  });

  it("холст не перехватывает мышь", () => {
    const { container } = render(<SituationCanvas strokes={[]} width={400} height={300} />);
    const canvas = container.querySelector("canvas") as HTMLCanvasElement;
    expect(canvas.getAttribute("aria-hidden")).toBe("true");
    expect(canvas.className).toBe("plan-situation");
  });
});
