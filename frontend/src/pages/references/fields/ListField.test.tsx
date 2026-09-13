// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ListField } from "./ListField";
import { sectionFields } from "../schemaFields";
import type { JsonSchemaObject } from "../../../types/referenceSchema";

afterEach(cleanup);

const CREW_SCHEMA: JsonSchemaObject = {
  type: "object",
  $defs: {
    CrewMember: {
      type: "object",
      properties: {
        position_code: { type: "string", title: "Должность", "x-ref": "positions" },
        headcount: {
          anyOf: [{ minimum: 0, type: "number" }, { type: "string" }],
          default: "1",
          title: "Численность",
          "x-unit": "чел",
        },
      },
    },
  },
  properties: {
    members: { type: "array", items: { $ref: "#/$defs/CrewMember" }, title: "Состав бригады" },
  },
};

const members = sectionFields(CREW_SCHEMA)[0];
const options = () => [{ code: "POS_A", name: "Машинист", is_active: true }];

describe("ListField: список объектов", () => {
  it("новая строка получает значения по умолчанию из схемы", () => {
    const onChange = vi.fn();
    render(<ListField field={members} value={[]} onChange={onChange} refOptions={options} />);
    fireEvent.click(screen.getByRole("button", { name: "+ Добавить строку" }));
    expect(onChange).toHaveBeenCalledWith([{ position_code: "", headcount: "1" }]);
  });

  it("ошибка сервера показывается под подполем своей строки", () => {
    render(
      <ListField
        field={members}
        value={[
          { position_code: "POS_A", headcount: "2" },
          { position_code: "POS_A", headcount: "x" },
        ]}
        onChange={() => undefined}
        refOptions={options}
        itemErrors={new Map([["1.headcount", "Численность: ожидается число"]])}
      />,
    );
    const inputs = screen.getAllByLabelText("Численность");
    expect(inputs).toHaveLength(2);
    expect(screen.getByText("Численность: ожидается число")).toBeInTheDocument();
    expect(inputs[1].closest(".ref-field")).toHaveClass("has-error");
    expect(inputs[0].closest(".ref-field")).not.toHaveClass("has-error");
  });

  it("ошибка всей строки показывается в её карточке", () => {
    render(
      <ListField
        field={members}
        value={[{ position_code: "POS_A", headcount: "1" }]}
        onChange={() => undefined}
        refOptions={options}
        itemErrors={new Map([["0", "Должность повторяется"]])}
      />,
    );
    expect(screen.getByText("Должность повторяется")).toBeInTheDocument();
  });

  it("id подполей не повторяются между строками", () => {
    const { container } = render(
      <ListField
        field={members}
        value={[
          { position_code: "POS_A", headcount: "1" },
          { position_code: "POS_A", headcount: "2" },
        ]}
        onChange={() => undefined}
        refOptions={options}
      />,
    );
    const ids = Array.from(container.querySelectorAll("[id]")).map((node) => node.id);
    expect(ids.length).toBeGreaterThan(0);
    expect(new Set(ids).size).toBe(ids.length);
  });
});
