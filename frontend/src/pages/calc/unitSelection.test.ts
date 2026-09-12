import { describe, expect, it } from "vitest";
import { filterObjectsByUnit, knownUnitCode, objectUnitCode, unitForLoadedSheet } from "./unitSelection";

const UNITS = [
  { code: "UNIT_PERM", name: "Юнит Пермь" },
  { code: "UNIT_URAL", name: "Юнит Урал" },
];

const OBJECTS = [
  { name: "Карьер Анна", production_unit_code: "UNIT_PERM" },
  { name: "Карьер Ломовской", production_unit_code: "UNIT_URAL" },
  { name: "Карьер без юнита", production_unit_code: null },
  { name: "Карьер из старой ревизии" },
];

describe("objectUnitCode", () => {
  it("возвращает юнит объекта", () => {
    expect(objectUnitCode(OBJECTS, "Карьер Анна")).toBe("UNIT_PERM");
  });

  it("пустая строка для объекта без юнита и для неизвестного объекта", () => {
    expect(objectUnitCode(OBJECTS, "Карьер без юнита")).toBe("");
    expect(objectUnitCode(OBJECTS, "Карьер из старой ревизии")).toBe("");
    expect(objectUnitCode(OBJECTS, "Нет такого")).toBe("");
  });
});

describe("filterObjectsByUnit", () => {
  const names = (unit: string, current = "") => filterObjectsByUnit(OBJECTS, unit, current).map((o) => o.name);

  it("без выбранного юнита показывает все объекты", () => {
    expect(names("")).toEqual(OBJECTS.map((o) => o.name));
  });

  it("оставляет объекты юнита и объекты без юнита, порядок как в справочнике", () => {
    expect(names("UNIT_PERM")).toEqual(["Карьер Анна", "Карьер без юнита", "Карьер из старой ревизии"]);
  });

  it("текущий объект остаётся в списке, даже если он из другого юнита", () => {
    expect(names("UNIT_PERM", "Карьер Ломовской")).toEqual([
      "Карьер Анна",
      "Карьер Ломовской",
      "Карьер без юнита",
      "Карьер из старой ревизии",
    ]);
  });
});

describe("knownUnitCode", () => {
  it("код из справочника остаётся", () => {
    expect(knownUnitCode(UNITS, "UNIT_URAL")).toBe("UNIT_URAL");
  });

  it("код, которого нет в опубликованной ревизии, сбрасывается — фильтр не должен прятать объекты", () => {
    expect(knownUnitCode(UNITS, "UNIT_CLOSED")).toBe("");
    expect(knownUnitCode([], "UNIT_PERM")).toBe("");
  });
});

describe("unitForLoadedSheet", () => {
  it("юнит объекта важнее перенесённого фильтра и сохранённого значения", () => {
    expect(unitForLoadedSheet(OBJECTS, "Карьер Анна", "UNIT_URAL", "UNIT_URAL")).toBe("UNIT_PERM");
  });

  it("у объекта без юнита при переходе из шапки сохраняется текущий фильтр", () => {
    expect(unitForLoadedSheet(OBJECTS, "Карьер без юнита", "UNIT_URAL", "UNIT_PERM")).toBe("UNIT_URAL");
    expect(unitForLoadedSheet(OBJECTS, "Карьер без юнита", "", "UNIT_PERM")).toBe("");
  });

  it("при открытии листа (без перехода из шапки) объект без юнита берёт сохранённый выбор", () => {
    expect(unitForLoadedSheet(OBJECTS, "Карьер без юнита", null, "UNIT_PERM")).toBe("UNIT_PERM");
  });
});
