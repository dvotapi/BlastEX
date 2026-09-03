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

const same = (left: Record<string, unknown>, right: Record<string, unknown>) =>
  fingerprint(item(left)) === fingerprint(item(right));

describe("fingerprint", () => {
  it("не различает число и его текстовую запись", () => {
    expect(same({ a: "1" }, { a: 1 })).toBe(true);
    expect(same({ a: "0.10" }, { a: 0.1 })).toBe(true);
    expect(same({ a: "-2.5" }, { a: -2.5 })).toBe(true);
  });

  it("не считает пустое значение отличием от отсутствующего", () => {
    expect(same({ a: "" }, {})).toBe(true);
    expect(same({ a: null }, {})).toBe(true);
    expect(same({ a: [] }, {})).toBe(true);
    expect(same({ a: {} }, {})).toBe(true);
  });

  it("нормализует вложенные списки и объекты", () => {
    expect(same({ a: [{ b: "2", c: "" }] }, { a: [{ b: 2 }] })).toBe(true);
    expect(same({ a: { b: { c: "3" } } }, { a: { b: { c: 3 } } })).toBe(true);
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
    expect(fingerprint(item({}))).not.toBe(fingerprint({ ...item({}), comment: "правка" }));
    expect(fingerprint(item({}))).not.toBe(fingerprint({ ...item({}), is_active: false }));
  });
});
