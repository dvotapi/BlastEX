// @vitest-environment jsdom
// Подвал окна импорта: площади, ошибки и предупреждения у «Построить блок».
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BuildFooter } from "./BuildFooter";
import { contourResult } from "./testing/fixtures";

afterEach(cleanup);

describe("BuildFooter", () => {
  it("площади и высота уступа коротко", () => {
    render(<BuildFooter result={contourResult()} pending={false} error="" onCancel={vi.fn()} onBuild={vi.fn()} />);
    expect(screen.getByText(/S верх 2789,9 м² · S низ 4120,9 м² · S ср 3455,4 м² · уступ 10,3 м/)).toBeTruthy();
  });

  it("без нижнего контура — прочерк без единиц, кнопка неактивна при ошибке", () => {
    render(
      <BuildFooter
        result={contourResult({ ok: false, bottom: null, mean_area_m2: null, issues: [{ code: "x", message: "Ошибка.", point: null }] })}
        pending={false}
        error=""
        onCancel={vi.fn()}
        onBuild={vi.fn()}
      />,
    );
    expect(screen.getByText(/S низ — · S ср —/)).toBeTruthy();
    expect((screen.getByRole("button", { name: "Построить блок" }) as HTMLButtonElement).disabled).toBe(true);
  });
});
