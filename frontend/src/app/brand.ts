/**
 * Бренд поставщика сервиса в шапке приложения.
 *
 * Не путать с `user.organization_name` (см. `types.ts`, `ReferencesPage.tsx`)
 * — то поле про организацию пользователя, оно per-account и приходит с
 * бэкенда; здесь — название и слоган самого BlastEX, одно на все аккаунты.
 * Вынесено отдельно от `AppShell.tsx`, чтобы смену бренда не искали в
 * компоненте маршрутизации страниц.
 */
export const BRAND = {
  mark: "EX",
  name: "Комплексные Решения",
  tagline: "EXcellence in mining",
} as const;
