import { describe, expect, it } from "vitest";
import { clampFaceAngleFromVertical, faceAngleFromVerticalInput } from "./faceAngle";

describe("угол откоса от вертикали", () => {
  it("обрезается до 0–60°", () => {
    expect(clampFaceAngleFromVertical(15)).toBe(15);
    expect(clampFaceAngleFromVertical(90)).toBe(60);
    expect(clampFaceAngleFromVertical(-3)).toBe(0);
  });

  it("пустой или нечисловой ввод оставляет прежний угол", () => {
    expect(faceAngleFromVerticalInput("", 15)).toBe(15);
    expect(faceAngleFromVerticalInput("abc", 20)).toBe(20);
    expect(faceAngleFromVerticalInput("80", 15)).toBe(60);
    expect(faceAngleFromVerticalInput("12", 15)).toBe(12);
  });
});
