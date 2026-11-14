// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { SurveyHelp } from "./SurveyHelp";

beforeAll(() => {
  HTMLDialogElement.prototype.showModal = vi.fn(function (this: HTMLDialogElement) {
    this.open = true;
  });
  HTMLDialogElement.prototype.close = vi.fn(function (this: HTMLDialogElement) {
    this.open = false;
  });
});
afterEach(cleanup);

describe("SurveyHelp", () => {
  it("объясняет файл, сопоставление, допуски и копию по съёмке", async () => {
    render(<SurveyHelp />);
    await userEvent.click(screen.getByRole("button", { name: "Справка по съёмке бурения" }));
    const help = screen.getByRole("dialog", { name: "Съёмка бурения: справка" }) as HTMLDialogElement;
    expect(help.open).toBe(true);
    const text = help.textContent ?? "";
    expect(text).toContain("L10.7");
    expect(text).toContain("Поменять");
    expect(text).toContain("Копия по съёмке");
    expect(text).toContain("отрицательный перебур");
  });
});
