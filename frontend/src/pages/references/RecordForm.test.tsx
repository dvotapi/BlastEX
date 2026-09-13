// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RecordForm, type DraftItem } from "./RecordForm";
import type { ReferenceSectionSchema } from "../../types/referenceSchema";
import type { ReferenceValidationIssue } from "../../types/economics";

afterEach(cleanup);

const SECTION: ReferenceSectionSchema = {
  code: "crew_templates",
  label: "Бригады",
  group: "labor",
  view: "table",
  deprecated: false,
  list_columns: [],
  fieldsets: [],
  json_schema: {
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
  },
};

const RECORD: DraftItem = {
  row_id: "row-1",
  code: "CREW_DRILL",
  name: "Бригада бурения",
  payload: { members: [{ position_code: "POS_A", headcount: 2 }] },
  is_active: true,
  valid_from: null,
  valid_to: null,
  source: "",
  comment: "",
  revision: 1,
};

function renderForm(onApply: (next: DraftItem) => void, issues: ReferenceValidationIssue[] = []) {
  return render(
    <RecordForm
      section={SECTION}
      record={RECORD}
      published={RECORD}
      issues={issues}
      canEdit
      isNew={false}
      changed={false}
      refOptions={() => [{ code: "POS_A", name: "Машинист", is_active: true }]}
      sectionLabels={{ positions: "Должности" }}
      siblings={[]}
      context={{ sections: {} }}
      vatRate={0.2}
      onApply={onApply}
      onReset={() => undefined}
      onDeactivate={() => undefined}
      onDuplicate={() => undefined}
      onClose={() => undefined}
    />,
  );
}

describe("RecordForm: списки объектов", () => {
  it("«Применить» без правок возвращает тот же payload", () => {
    const onApply = vi.fn();
    renderForm(onApply);
    fireEvent.click(screen.getByRole("button", { name: "Применить" }));
    expect(onApply.mock.calls[0][0].payload).toEqual(RECORD.payload);
  });

  it("запятая в числе подполя сохраняется точкой, пустое обязательное — не сохраняется", () => {
    const onApply = vi.fn();
    renderForm(onApply);
    fireEvent.click(screen.getByRole("button", { name: "+ Добавить строку" }));
    const [first, second] = screen.getAllByLabelText("Численность");
    fireEvent.change(first, { target: { value: "2,5" } });
    fireEvent.change(second, { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Применить" }));
    // Во второй строке оба подполя обязательные и пустые: ключи не сохраняются,
    // сервер подставит умолчание численности и сообщит о пустой должности.
    expect(onApply.mock.calls[0][0].payload).toEqual({
      members: [{ position_code: "POS_A", headcount: "2.5" }, {}],
    });
  });

  it("ошибка проверки ревизии видна под подполем строки", () => {
    renderForm(() => undefined, [
      {
        level: "error",
        section: "crew_templates",
        code: "CREW_DRILL",
        message: "Состав бригады → строка 1 → Численность: ожидается число",
        field: "members.0.headcount",
      },
    ]);
    expect(screen.getByText("Состав бригады → строка 1 → Численность: ожидается число")).toBeInTheDocument();
  });
});
