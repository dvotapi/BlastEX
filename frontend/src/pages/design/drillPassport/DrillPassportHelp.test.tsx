// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { DrillPassportHelp } from "./DrillPassportHelp";

beforeAll(() => {
  HTMLDialogElement.prototype.showModal = vi.fn(function (this: HTMLDialogElement) {
    this.open = true;
  });
  HTMLDialogElement.prototype.close = vi.fn(function (this: HTMLDialogElement) {
    this.open = false;
  });
});
afterEach(cleanup);

describe("DrillPassportHelp", () => {
  it("объясняет s, первый ряд, профиль приёмника и локализацию МСК", async () => {
    render(<DrillPassportHelp />);
    await userEvent.click(screen.getByRole("button", { name: "Справка по паспорту на бурение" }));
    const help = screen.getByRole("dialog", { name: "Паспорт на бурение: справка" }) as HTMLDialogElement;
    expect(help.open).toBe(true);
    const text = help.textContent ?? "";
    expect(text).toContain("s = ");
    expect(text).toContain("Первый ряд");
    expect(text).toContain("PNEZD");
    expect(text).toMatch(/локализац/);
    expect(text).toContain("МСК");
    expect(text).toContain("Сохранить как");
  });
});
