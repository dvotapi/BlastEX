/**
 * Сравнение двух вариантов заряда на листе «Расчёт»: какие строки таблиц
 * «Скважина» и «Блок» показать рядом («Отличаются между вариантами»), а какие —
 * один раз («Общее для обоих»).
 *
 * Строки приходят с бэкенда уже подписанными и отформатированными
 * (`hole_rows` / `block_rows` ответа `POST /blast/geometry`, собираются в
 * `cost/geometry.py`), ключей у них нет — связываем по подписи. Состав
 * отличий описан только здесь: если подписи на бэкенде поменяются, правится
 * этот файл. Модуль чистый — без React и запросов.
 */

export type Row = [label: string, value: string];

/** Строки скважины, которые зависят от параметров варианта заряда. */
export const DIFF_HOLE_LABELS = [
  "Недозаряд, м",
  "Длина заряда, м",
  "Вместимость, кг/п.м.",
  "Заряд, кг",
  "Удельный, кг/м³",
  "Замедление, мс",
  "Пром. детонаторы, шт/скв",
  "Скважинное НСИ, шт/скв",
  "Длина скважинного НСИ-1, м",
  "Длина скважинного НСИ-2, м",
] as const;

/** Строки блока, которые зависят от параметров варианта заряда. */
export const DIFF_BLOCK_LABELS = [
  "Масса ВВ на блок, кг",
  "Удельный с доп., кг/м³",
  "Пром. детонаторы, шт",
  "НСИ скважинное, шт",
  "Боевики на НСИ, шт",
  "Длина скважинного НСИ на блок, м",
] as const;

/** Строка сравнения. `null` — строки нет в ответе этого варианта.
 * `flag` — строка вне фиксированного состава, но значения различаются. */
export type DiffRow = { label: string; a: string | null; b: string | null; flag: boolean };
export type SharedRow = { label: string; value: string };
export type Comparison = { diffHole: DiffRow[]; diffBlock: DiffRow[]; shared: SharedRow[] };

/**
 * Подписи обоих вариантов в порядке ответа: сначала первого, затем
 * недостающие второго — каждая перед той подписью первого, за которой она
 * идёт у второго варианта. Так строка, которая есть только у одного варианта
 * (НСИ-2), встаёт на своё место, а не в конец.
 */
function unionLabels(a: Row[], b: Row[]): string[] {
  const order = a.map(([label]) => label);
  const known = new Set(order);
  b.forEach(([label], index) => {
    if (known.has(label)) return;
    // Ближайшая следующая подпись второго варианта, которая есть в списке.
    const next = b.slice(index + 1).find(([candidate]) => known.has(candidate));
    const at = next ? order.indexOf(next[0]) : order.length;
    order.splice(at, 0, label);
    known.add(label);
  });
  return order;
}

function splitSection(a: Row[], b: Row[], diffLabels: readonly string[]): { diff: DiffRow[]; shared: SharedRow[] } {
  const valuesA = new Map(a);
  const valuesB = new Map(b);
  const fixed = new Set(diffLabels);
  const diff: DiffRow[] = [];
  const shared: SharedRow[] = [];
  for (const label of unionLabels(a, b)) {
    const va = valuesA.get(label) ?? null;
    const vb = valuesB.get(label) ?? null;
    if (fixed.has(label)) diff.push({ label, a: va, b: vb, flag: false });
    else if (va !== null && va === vb) shared.push({ label, value: va });
    else diff.push({ label, a: va, b: vb, flag: true });
  }
  return { diff, shared };
}

export function splitComparison(holeA: Row[], holeB: Row[], blockA: Row[], blockB: Row[]): Comparison {
  const hole = splitSection(holeA, holeB, DIFF_HOLE_LABELS);
  const block = splitSection(blockA, blockB, DIFF_BLOCK_LABELS);
  return { diffHole: hole.diff, diffBlock: block.diff, shared: [...hole.shared, ...block.shared] };
}
