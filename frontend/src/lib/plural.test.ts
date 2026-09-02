import { describe, expect, it } from "vitest";
import { plural } from "./plural";

const FORMS: [string, string, string] = ["станок", "станка", "станков"];

describe("русская форма по числу", () => {
  it("единственное число", () => {
    expect(plural(1, FORMS)).toBe("станок");
    expect(plural(21, FORMS)).toBe("станок");
  });

  it("от двух до четырёх", () => {
    expect(plural(2, FORMS)).toBe("станка");
    expect(plural(43, FORMS)).toBe("станка");
  });

  it("множественное число и подростковые числа", () => {
    expect(plural(0, FORMS)).toBe("станков");
    expect(plural(5, FORMS)).toBe("станков");
    expect(plural(11, FORMS)).toBe("станков");
    expect(plural(14, FORMS)).toBe("станков");
    expect(plural(112, FORMS)).toBe("станков");
  });
});
