// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { OriginBadge } from "./OriginBadge";

describe("OriginBadge", () => {
  it("подписывает происхождение словом, а не кодом", () => {
    render(<OriginBadge origin="PASSPORT" />);
    expect(screen.getByText("Паспорт")).toHaveAttribute("title", "Величина из технического паспорта");
  });

  it("ничего не рисует без происхождения", () => {
    const { container } = render(<OriginBadge origin="" />);
    expect(container).toBeEmptyDOMElement();
  });
});
