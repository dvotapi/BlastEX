/**
 * Бренд поставщика сервиса в шапке приложения.
 *
 * Не путать с `user.organization_name` (см. `types.ts`, `ReferencesPage.tsx`)
 * — то поле про организацию пользователя, оно per-account и приходит с
 * бэкенда; здесь — название и слоган самого сервиса, одно на все аккаунты.
 * Знак и логотип — векторные компоненты `assets/ComplexMark.tsx` и
 * `assets/ComplexLogo.tsx`. Слоган разбит на части, потому что «EX» в нём
 * выделяется цветом бренда.
 */
export const BRAND = {
  name: "Комплексные Решения",
  taglineAccent: "EX",
  taglineRest: "cellence in mining",
} as const;
