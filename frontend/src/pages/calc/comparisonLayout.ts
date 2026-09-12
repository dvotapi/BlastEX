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
 * `flag` — строка вне фиксированного состава, но значения различаются.
 * `key` — уникален в пределах сравнения, даже если подпись в ответе повторяется. */
export type DiffRow = { key: string; label: string; a: string | null; b: string | null; flag: boolean };
export type SharedRow = { key: string; label: string; value: string };
export type Comparison = { diffHole: DiffRow[]; diffBlock: DiffRow[]; shared: SharedRow[] };

type Keyed = { key: string; label: string; value: string };

/** Ключ строки — подпись и номер её повторения в ответе: подписи в ответе
 * бэкенда не обязаны быть уникальными (например, пустой разделитель). */
function keyed(section: string, rows: Row[]): Keyed[] {
  const seen = new Map<string, number>();
  return rows.map(([label, value]) => {
    const occurrence = seen.get(label) ?? 0;
    seen.set(label, occurrence + 1);
    return { key: `${section}:${label}#${occurrence}`, label, value };
  });
}

/**
 * Ключи обоих вариантов в порядке ответа: сначала первого, затем недостающие
 * второго — каждый перед тем ключом первого, за которым он идёт у второго
 * варианта. Так строка, которая есть только у одного варианта (НСИ-2), встаёт
 * на своё место, а не в конец.
 */
function unionKeys(a: Keyed[], b: Keyed[]): string[] {
  const order = a.map((row) => row.key);
  const known = new Set(order);
  b.forEach((row, index) => {
    if (known.has(row.key)) return;
    const next = b.slice(index + 1).find((candidate) => known.has(candidate.key));
    const at = next ? order.indexOf(next.key) : order.length;
    order.splice(at, 0, row.key);
    known.add(row.key);
  });
  return order;
}

function splitSection(section: string, rowsA: Row[], rowsB: Row[], diffLabels: readonly string[]): { diff: DiffRow[]; shared: SharedRow[] } {
  const a = keyed(section, rowsA);
  const b = keyed(section, rowsB);
  const byKeyA = new Map(a.map((row) => [row.key, row]));
  const byKeyB = new Map(b.map((row) => [row.key, row]));
  const fixed = new Set(diffLabels);
  const diff: DiffRow[] = [];
  const shared: SharedRow[] = [];
  for (const key of unionKeys(a, b)) {
    const rowA = byKeyA.get(key);
    const rowB = byKeyB.get(key);
    const label = (rowA ?? rowB)!.label;
    const va = rowA?.value ?? null;
    const vb = rowB?.value ?? null;
    if (fixed.has(label)) diff.push({ key, label, a: va, b: vb, flag: false });
    else if (va !== null && va === vb) shared.push({ key, label, value: va });
    else diff.push({ key, label, a: va, b: vb, flag: true });
  }
  return { diff, shared };
}

export function splitComparison(holeA: Row[], holeB: Row[], blockA: Row[], blockB: Row[]): Comparison {
  const hole = splitSection("hole", holeA, holeB, DIFF_HOLE_LABELS);
  const block = splitSection("block", blockA, blockB, DIFF_BLOCK_LABELS);
  return { diffHole: hole.diff, diffBlock: block.diff, shared: [...hole.shared, ...block.shared] };
}
