import type { ModelParameters } from "../../types/blockEconomics";

/** Четыре колонки — предел читаемой таблицы и предел бумажной сметы (см. VariantsRequest на бэкенде). */
export const MAX_VARIANTS = 4;

/** Один столбец сметы на вкладке: своё имя и полный набор параметров. */
export type Variant = {
  id: string;
  name: string;
  parameters: ModelParameters;
};

function variantId(): string {
  const token =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `variant-${token}`;
}

/** Первый вариант вкладки — вокруг него строится дублирование остальных. */
export function makeVariant(name: string, parameters: ModelParameters): Variant {
  return { id: variantId(), name, parameters };
}

/** Добавить готовый вариант в конец; сверх предела список не растёт. */
export function addVariant(variants: Variant[], variant: Variant): Variant[] {
  if (variants.length >= MAX_VARIANTS) return variants;
  return [...variants, variant];
}

/**
 * Копия активного варианта с новым именем — так сметчик меняет одно поле
 * и сравнивает с исходным, а не набирает вариант заново.
 */
export function duplicateVariant(variants: Variant[], id: string): Variant[] {
  const base = variants.find((variant) => variant.id === id);
  if (!base) return variants;
  return addVariant(variants, {
    id: variantId(),
    name: `Вариант ${variants.length + 1}`,
    parameters: { ...base.parameters },
  });
}

/** Последний вариант не удаляется: пустой сметы не бывает. */
export function removeVariant(variants: Variant[], id: string): Variant[] {
  if (variants.length <= 1) return variants;
  return variants.filter((variant) => variant.id !== id);
}

export function renameVariant(variants: Variant[], id: string, name: string): Variant[] {
  return variants.map((variant) => (variant.id === id ? { ...variant, name } : variant));
}

/** Правка параметров одного варианта — тот же приём, что `patchParams` для одиночного расчёта. */
export function patchVariant(
  variants: Variant[],
  id: string,
  patch: Partial<ModelParameters>,
): Variant[] {
  return variants.map((variant) =>
    variant.id === id ? { ...variant, parameters: { ...variant.parameters, ...patch } } : variant,
  );
}
