import { describe, expect, it } from "vitest";
import {
  clampFaceAngleFromVertical,
  faceAngleForImportedBlock,
  faceAngleFromVerticalInput,
  faceAngleReplacedOnImport,
} from "./faceAngle";

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

describe("угол откоса после «Построить блок»", () => {
  it("90° заменяется углом объекта, и об этом надо сказать", () => {
    expect(faceAngleForImportedBlock(90)).toBe(75);
    expect(faceAngleReplacedOnImport(90)).toBe(true);
  });

  it("заданный угол остаётся без сообщения", () => {
    expect(faceAngleForImportedBlock(70)).toBe(70);
    expect(faceAngleReplacedOnImport(70)).toBe(false);
    expect(faceAngleReplacedOnImport(undefined)).toBe(false);
  });
});
