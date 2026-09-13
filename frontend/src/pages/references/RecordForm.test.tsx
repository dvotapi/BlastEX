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

function formElement(
  onApply: (next: DraftItem) => void,
  issues: ReferenceValidationIssue[] = [],
  record: DraftItem = RECORD,
) {
  return (
    <RecordForm
      section={SECTION}
      record={record}
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
    />
  );
}

function renderForm(onApply: (next: DraftItem) => void, issues: ReferenceValidationIssue[] = []) {
  return render(formElement(onApply, issues));
}

describe("RecordForm: списки объектов", () => {
  it("«Применить» без правок возвращает тот же payload", () => {
    const onApply = vi.fn();
    renderForm(onApply);
    fireEvent.click(screen.getByRole("button", { name: "Применить" }));
    expect(onApply.mock.calls[0][0].payload).toEqual(RECORD.payload);
  });

  it("«Применить» без правок не трогает строку с пустой должностью из старой записи", () => {
    const onApply = vi.fn();
    const legacy: DraftItem = {
      ...RECORD,
      payload: { members: [{ position_code: "", headcount: "1" }, { position_code: "POS_A", headcount: 2 }] },
    };
    render(formElement(onApply, [], legacy));
    fireEvent.click(screen.getByRole("button", { name: "Применить" }));
    expect(onApply.mock.calls[0][0].payload).toEqual(legacy.payload);
  });

  it("правка строки со старой пустой должностью нормализует эту строку", () => {
    const onApply = vi.fn();
    const legacy: DraftItem = {
      ...RECORD,
      payload: { members: [{ position_code: "", headcount: "1" }, { position_code: "POS_A", headcount: 2 }] },
    };
    render(formElement(onApply, [], legacy));
    fireEvent.change(screen.getAllByLabelText("Численность")[0], { target: { value: "3" } });
    fireEvent.click(screen.getByRole("button", { name: "Применить" }));
    // Пустая должность в изменённой строке не сохраняется: проверка ревизии
    // покажет ошибку под полем той строки, которую сметчик сейчас правит.
    expect(onApply.mock.calls[0][0].payload).toEqual({
      members: [{ headcount: "3" }, { position_code: "POS_A", headcount: 2 }],
    });
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

  it("очищенное обязательное подполе после «Применить» показывает умолчание схемы", () => {
    const onApply = vi.fn();
    const { rerender } = renderForm(onApply);
    fireEvent.change(screen.getByLabelText("Численность"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Применить" }));

    const payload = onApply.mock.calls[0][0].payload;
    expect(payload).toEqual({ members: [{ position_code: "POS_A" }] });

    // `record` — константа, useEffect формы реагирует на смену записи:
    // пересобираем форму с payload из onApply, чтобы проверить отображение.
    rerender(formElement(onApply, [], { ...RECORD, payload }));
    expect(screen.getByLabelText("Численность")).toHaveValue("1");
  });

  it("ошибка строки, которой уже нет в форме, видна в общем блоке", () => {
    renderForm(() => undefined, [
      {
        level: "error",
        section: "crew_templates",
        code: "CREW_DRILL",
        message: "Не заполнено обязательное поле «Состав бригады → строка 3 → Должность».",
        field: "members.2.position_code",
      },
    ]);
    expect(
      screen.getByText("Не заполнено обязательное поле «Состав бригады → строка 3 → Должность».").closest(".ref-form-issues"),
    ).not.toBeNull();
  });

  it("две ошибки одного подполя видны обе под этим подполем", () => {
    renderForm(() => undefined, [
      {
        level: "error",
        section: "crew_templates",
        code: "CREW_DRILL",
        message: "Первая ошибка должности.",
        field: "members.0.position_code",
      },
      {
        level: "error",
        section: "crew_templates",
        code: "CREW_DRILL",
        message: "Вторая ошибка должности.",
        field: "members.0.position_code",
      },
    ]);
    const error = screen.getByLabelText("Должность").closest(".ref-field")?.querySelector(".ref-field-error");
    expect(error?.textContent).toContain("Первая ошибка должности.");
    expect(error?.textContent).toContain("Вторая ошибка должности.");
  });

  it("ошибка лишнего ключа подполя (extra=forbid) видна в общем блоке", () => {
    renderForm(() => undefined, [
      {
        level: "error",
        section: "crew_templates",
        code: "CREW_DRILL",
        message: "Состав бригады → строка 1: неизвестное поле unknown_key",
        field: "members.0.unknown_key",
      },
    ]);
    expect(screen.getByText("Состав бригады → строка 1: неизвестное поле unknown_key")).toBeInTheDocument();
  });
});
