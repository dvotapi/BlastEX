// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { useWorkspace } from "../app/useWorkspace";
import { renderWithWorkspace } from "./render";
import { screen } from "@testing-library/react";

function Probe() {
  const { canEdit } = useWorkspace();
  return <span>{canEdit ? "можно редактировать" : "только чтение"}</span>;
}

describe("renderWithWorkspace", () => {
  it("даёт компоненту рабочий контекст рабочего пространства", () => {
    renderWithWorkspace(<Probe />);
    expect(screen.getByText("можно редактировать")).toBeInTheDocument();
  });
  it("позволяет переопределить canEdit", () => {
    renderWithWorkspace(<Probe />, { canEdit: false });
    expect(screen.getByText("только чтение")).toBeInTheDocument();
  });
});
