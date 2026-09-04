import { describe, expect, it } from "vitest";
import { fingerprint } from "./fingerprint";
import type { EconomicsReferenceItem } from "../../types/economics";

function item(payload: Record<string, unknown>): EconomicsReferenceItem {
  return {
    code: "SITE_A",
    name: "Карьер А",
    payload,
    is_active: true,
    valid_from: null,
    valid_to: null,
    source: "Смета",
    comment: "",
    revision: 1,
  };
}

const numeric = new Set(["a"]);
const text = new Set<string>();

const same = (
  left: Record<string, unknown>,
  right: Record<string, unknown>,
  keys: ReadonlySet<string> = numeric,
) => fingerprint(item(left), keys) === fingerprint(item(right), keys);

describe("fingerprint", () => {
  it("не различает число и его текстовую запись в числовом поле", () => {
    expect(same({ a: "1" }, { a: 1 })).toBe(true);
    expect(same({ a: "0.10" }, { a: 0.1 })).toBe(true);
    expect(same({ a: "-2.5" }, { a: -2.5 })).toBe(true);
  });

  it("не трогает текстовые поля из цифр", () => {
    // ИНН «0021» и «21» — разные контрагенты, а не одно число.
    expect(same({ a: "0021" }, { a: "21" }, text)).toBe(false);
    expect(same({ a: "00000000000000000001" }, { a: "00000000000000000002" }, text)).toBe(false);
    expect(fingerprint(item({ a: "0021" }), text)).toContain("0021");
  });

  it("не приводит числа внутри списков и объектов", () => {
    // Состав вложенных структур схема здесь не описывает: молчаливое
    // приведение съело бы инвентарный номер «007» в строке списка.
    expect(same({ a: [{ b: "007" }] }, { a: [{ b: 7 }] })).toBe(false);
    expect(same({ a: [{ b: "2", c: "" }] }, { a: [{ b: "2" }] })).toBe(true);
    expect(same({ a: { b: { c: "3" } } }, { a: { b: { c: "3" } } })).toBe(true);
  });

  it("не считает пустое значение отличием от отсутствующего", () => {
    expect(same({ a: "" }, {})).toBe(true);
    expect(same({ a: null }, {})).toBe(true);
    expect(same({ a: [] }, {})).toBe(true);
    expect(same({ a: {} }, {})).toBe(true);
  });

  it("не зависит от порядка ключей", () => {
    expect(same({ a: 1, b: 2 }, { b: 2, a: 1 })).toBe(true);
  });

  it("видит настоящие различия", () => {
    expect(same({ a: "abc" }, { a: "abd" })).toBe(false);
    expect(same({ a: "1" }, { a: "2" })).toBe(false);
    expect(same({ a: "1" }, { a: true })).toBe(false);
  });

  it("учитывает поля записи помимо payload", () => {
    expect(fingerprint(item({}), text)).not.toBe(fingerprint({ ...item({}), comment: "правка" }, text));
    expect(fingerprint(item({}), text)).not.toBe(fingerprint({ ...item({}), is_active: false }, text));
  });
});
