import { describe, expect, it } from "vitest";

import {
  NOMENCLATURE_ROLES,
  isRoleVisible,
  optionCaption,
  roleQuantity,
  unitLabel,
} from "./nomenclature";
import type { TechnicalPassport } from "../../types/blockEconomics";

const passport = {
  physical: { explosive_kg: "29038.86", downhole_nsi: "189", start_nsi: "0" },
} as unknown as TechnicalPassport;

const role = (code: string) => NOMENCLATURE_ROLES.find((item) => item.role === code)!;

describe("роли номенклатуры", () => {
  it("берёт количество из паспорта", () => {
    expect(roleQuantity(role("EXPLOSIVE"), passport)).toBe(29038.86);
  });

  it("прячет роль, которой нет в блоке", () => {
    expect(isRoleVisible(role("NSI_START"), passport)).toBe(false);
    expect(isRoleVisible(role("NSI_DOWNHOLE"), passport)).toBe(true);
  });

  it("роль без драйвера показывается всегда: её количество задаёт сметчик", () => {
    expect(isRoleVisible(role("DETONATOR_ELECTRIC"), passport)).toBe(true);
    expect(roleQuantity(role("DETONATOR_ELECTRIC"), passport)).toBeNull();
  });

  it("без паспорта роль с драйвером не показывается", () => {
    expect(isRoleVisible(role("EXPLOSIVE"), null)).toBe(false);
  });
});

describe("подпись под выбором", () => {
  it("показывает цену за единицу", () => {
    const caption = optionCaption(
      { code: "MAT_VV_EVERSIN", name: "Эверсин", unit: "KG", price_rub: 48.9, length_m: 0 },
      role("EXPLOSIVE"),
    );
    expect(caption).toBe("48,90 ₽ за кг");
  });

  it("называет незаполненную цену", () => {
    const caption = optionCaption(
      { code: "MAT_X", name: "Протолит", unit: "KG", price_rub: 0, length_m: 0 },
      role("EXPLOSIVE"),
    );
    expect(caption).toBe("нет цены в справочнике");
  });

  it("без выбора подсказывает, откуда возьмётся количество", () => {
    expect(optionCaption(undefined, role("EXPLOSIVE"))).toBe("масса заряда из паспорта");
  });

  it("объясняет пустой список: в справочнике нет позиций этой роли", () => {
    expect(optionCaption(undefined, role("EXPLOSIVE"), 0)).toBe(
      "в справочнике нет таких позиций",
    );
  });

  it("переводит код единицы в подпись", () => {
    expect(unitLabel("PIECE")).toBe("шт");
    expect(unitLabel("KG")).toBe("кг");
  });
});
