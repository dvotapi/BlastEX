import { describe, expect, it } from "vitest";

import { NOMENCLATURE_ROLES, isRoleVisible, optionCaption, roleQuantity } from "./nomenclature";
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
  it("показывает цену за единицу и количество на блок", () => {
    const caption = optionCaption(
      {
        code: "MAT_VV_EVERSIN", name: "Эверсин", unit: "кг", price_rub: 48.9, length_m: 0,
        quantity: 29038.86, quantity_label: "",
      },
      role("EXPLOSIVE"),
    );
    // Разряды тысяч Intl разделяет неразрывным пробелом.
    expect(caption).toBe("48,90 ₽ за кг · 29\u00a0038,86 кг на блок");
  });

  it("для боевиков показывает килограммы с переводом из штук", () => {
    const caption = optionCaption(
      {
        code: "MAT_BOOSTER", name: "Сферит", unit: "кг", price_rub: 150, length_m: 0,
        quantity: 979.2, quantity_label: "1224 шт × 0.8 кг",
      },
      role("BOOSTER"),
    );
    expect(caption).toBe("150,00 ₽ за кг · 979,2 кг на блок (1224 шт × 0.8 кг)");
  });

  it("ручная роль — только цена", () => {
    const caption = optionCaption(
      { code: "MAT_ED", name: "ЭД-1-Н", unit: "шт", price_rub: 45, length_m: 0, quantity: null, quantity_label: "" },
      role("DETONATOR_ELECTRIC"),
    );
    expect(caption).toBe("45,00 ₽ за шт");
  });

  it("называет незаполненную цену", () => {
    const caption = optionCaption(
      { code: "MAT_X", name: "Протолит", unit: "кг", price_rub: 0, length_m: 0, quantity: 100, quantity_label: "" },
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
});
