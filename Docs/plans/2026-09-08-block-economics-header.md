# Вкладка «Экономика блока»: шапка в одну строку и полоса паспорта с плашками

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Шапка приложения становится одной строкой чуть выше кнопок; под ней на вкладке «Экономика блока» — полоса паспорта: объект, паспорт, ревизия, имя сценария и кнопка сохранения в одну строку, ниже четыре плашки геометрии (объём, погонаж, скважины, выход метров с одной скважины), остальные величины паспорта — под раскрывашкой. Полоса закреплена при прокрутке.

**Architecture:** Шапка общая для всех вкладок (`AppShell.tsx`): заголовок, слот заголовка (туда «Справка» попадает порталом), бренд, слот полосы листа «Расчёт» и «Выйти» встают в один flex-ряд. Полоса паспорта — новый компонент `PassportStrip.tsx`, живущий вне `.page-content`, чтобы примыкать к шапке без полей страницы; числа плашек и строки полной таблицы считает чистый модуль `passportSummary.ts` (там же — производный показатель «метров с одной скважины»). Липкая колонка параметров отступает на высоту липкой полосы через CSS-переменную, которую страница обновляет по `ResizeObserver`.

**Tech Stack:** React 19 + TypeScript + Vite, vitest (environment `node`, тесты только для чистых функций), обычный CSS в `frontend/src/styles.css`.

**Spec:** решения приняты в чате 2026-09-08 по эскизу «B — полоса»:
- шапка одной строкой ~48px: «Экономика блока», «Справка», лого «EX» с названием и слоганом, справа «Выйти»; правило общее для всех вкладок;
- следующая строка: Объект работ · Технический паспорт · Ревизия справочников · Имя сценария · «Сохранить сценарий»;
- следующая строка: плашки «Объём блока», «Погонаж бурения», «Скважины», «С одной скважины» (погонаж ÷ скважины, один знак) — тем же видом, что плашки листа «Расчёт» (`.metric-chip`);
- Масса ВВ, скважинные и поверхностные НСИ и колонка «Источник» — под раскрывашкой «Все показатели паспорта и источники»;
- полоса закреплена при прокрутке (кроме телефонов).

## Global Constraints

- Ветка: новая `feat/block-economics-header` от текущего `HEAD` ветки `feat/block-economics-variants` (страница зависит от уже закоммиченных вариантов). В рабочем дереве есть чужие незакоммиченные правки (`api/`, `cost/`, `frontend/src/pages/economics/estimateSections*`, `tests/`) — их не трогать и не добавлять в коммиты: `git add` только по путям из задачи.
- Тексты интерфейса и комментарии — по-русски; сообщения коммитов — как в истории (`feat(...)`, `fix(...)`), с трейлером `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Числа — русской записью через `amount()` из `frontend/src/pages/economics/format.ts` (неразрывный пробел тысяч, запятая).
- Никаких новых зависимостей; никаких компонентных тестов (в проекте нет DOM-окружения) — тестируются чистые функции.
- Команды проверки: `cd frontend && npx vitest run` и `cd frontend && npm run build` (`tsc -b` + `vite build`).

## Структура файлов

| Файл | Ответственность |
|---|---|
| `frontend/src/app/AppShell.tsx` (изменить) | шапка: заголовок, слот заголовка, бренд — один ряд `.topbar-lead` |
| `frontend/src/styles.css` (изменить) | `.topbar` в одну строку; стили `.passport-strip*`; липкость и отступ колонки параметров; удаление мёртвых `.block-economics-passport` |
| `frontend/src/pages/economics/passportSummary.ts` (создать) + `.test.ts` | плашки (4 шт., с производным «метров с одной скважины») и строки полной таблицы паспорта |
| `frontend/src/pages/economics/PassportStrip.tsx` (создать) | полоса паспорта: поля, кнопка, статус, плашки, раскрывашка с таблицей |
| `frontend/src/lib/useElementHeight.ts` (создать) | хук: высота узла через `ResizeObserver`, callback-ref |
| `frontend/src/pages/economics/BlockEconomicsPage.tsx` (изменить) | использует `PassportStrip`, убирает панель паспорта и `.page-heading`, задаёт `--passport-strip-h` |

---

### Task 1: Шапка приложения в одну строку

**Files:**
- Modify: `frontend/src/app/AppShell.tsx` (блок `<header className="topbar">`)
- Modify: `frontend/src/styles.css` (правила `.topbar`, `.topbar > div`, `.topbar-title-row`, `.topbar-brand`, медиазапрос `max-width:760px`)

**Interfaces:**
- Produces: узлы `topbar-title-slot` и `topbar-slot` остаются с теми же именами — `topbarSlot.tsx`, `EconomicsHelp.tsx`, `CalcPage.tsx` не меняются.

Сейчас левый блок шапки — grid из двух строк (заголовок со слотом; бренд под ним), отчего шапка выше 100px. Становится одним flex-рядом; высота задаётся `min-height:48px` при кнопке «Выйти» в 34px. Правило `.topbar b { font-size:17px }` уходит — оно било по всем `b` в шапке, и бренд с полосой «Расчёта» перебивали его порядком объявления; заголовок получает свой класс.

- [ ] **Step 1: Переписать разметку шапки**

В `AppShell.tsx` заменить содержимое `<header className="topbar">` на:

```tsx
<header className="topbar">
  <div className="topbar-lead">
    <b className="topbar-title">{TITLES[page]}</b>
    <div className="topbar-title-slot" ref={setTitleSlot} />
    {/* Бренд поставщика сервиса — не орг-данные пользователя: та же
        строка раньше показывала `user.organization_name`, это поле
        осталось (см. ReferencesPage.tsx), здесь только вид сменился. */}
    <div className="topbar-brand">
      <span className="topbar-brand-mark" aria-hidden="true">{BRAND.mark}</span>
      <span className="topbar-brand-text">
        <b>{BRAND.name}</b>
        <i>{BRAND.tagline}</i>
      </span>
    </div>
  </div>
  <div className="topbar-slot" ref={setTopbarSlot} />
  <button className="logout-button" onClick={onLogout}>Выйти</button>
</header>
```

- [ ] **Step 2: Стили шапки**

В `styles.css` заменить две строки

```css
.topbar { height:auto; min-height:72px; padding:10px 28px; display:flex; align-items:center; justify-content:space-between; gap:18px; border-bottom:1px solid #dce4e0; background:#fff; }
.topbar > div { display:grid; gap:4px; }.topbar b { font-size:17px; }.topbar span { color:#69776f; font-size:11px; }
```

на

```css
/* Одна строка чуть выше кнопок («Выйти» — 34px): заголовок, слот заголовка
   («Справка» экономики), бренд, слот полосы листа «Расчёт» и «Выйти».
   Высота не фиксирована: полоса «Расчёта» с плашками при узком окне
   переносится и растит шапку, но по умолчанию всё умещается в один ряд. */
.topbar { min-height:48px; padding:6px 28px; display:flex; align-items:center; justify-content:space-between; gap:18px; border-bottom:1px solid #dce4e0; background:#fff; }
.topbar-lead { display:flex; align-items:center; gap:14px; flex:none; min-width:0; }
.topbar-title { font-size:17px; white-space:nowrap; }
.topbar span { color:#69776f; font-size:11px; }
```

Удалить строку `.topbar-title-row { display:flex; align-items:center; gap:10px; }` и заменить `.topbar-brand { display:flex; align-items:center; gap:7px; }` на

```css
.topbar-brand { display:flex; align-items:center; gap:7px; padding-left:14px; border-left:1px solid #e2e8e5; }
```

В комментарии над `.topbar > .topbar-slot` убрать упоминание правила `.topbar > div` (его больше нет), селектор оставить.

В медиазапросе `@media (max-width:760px)` заменить `.topbar { height:64px; padding:0 16px; }.topbar-brand-text i { display:none; }` на `.topbar { min-height:56px; padding:6px 16px; }.topbar-brand-text { display:none; }` — на телефоне в один ряд с заголовком и «Выйти» помещается только значок «EX».

- [ ] **Step 3: Сборка и тесты**

Run: `cd frontend && npm run build && npx vitest run`
Expected: сборка без ошибок, 194 теста PASS.

- [ ] **Step 4: Проверить в браузере**

Запустить `api` и `frontend` из `.claude/launch.json` (учётка — см. память `local-dev-setup`). На вкладке «Экономика»: `document.querySelector(".topbar").offsetHeight` — около 48; заголовок, «Справка», бренд и «Выйти» в одном ряду. На вкладке «Расчёт»: полоса с плашками осталась в шапке справа от бренда, не наезжает на «Выйти». В режиме «Проектирование» шапка по-прежнему 36px и без левого блока.

- [ ] **Step 5: Коммит**

```bash
git checkout -b feat/block-economics-header
git add frontend/src/app/AppShell.tsx frontend/src/styles.css
git commit -m "feat(ui): шапка приложения в одну строку — заголовок, бренд и кнопки рядом"
```

---

### Task 2: Плашки и строки паспорта — чистый модуль

**Files:**
- Create: `frontend/src/pages/economics/passportSummary.ts`
- Test: `frontend/src/pages/economics/passportSummary.test.ts`

**Interfaces:**
- Consumes: `amount(value: number): string` из `./format`; `Numeric` из `../../types/blockEconomics`.
- Produces:
  - `type PassportMetric = { key: string; label: string; value: string; unit: string }`
  - `type PassportRow = PassportMetric & { source: string }`
  - `passportMetrics(physical: Record<string, Numeric>): PassportMetric[]` — ровно четыре, в порядке чтения;
  - `passportRows(physical: Record<string, Numeric>, lineage: Record<string, string>): PassportRow[]` — только посчитанные величины.

Константа `GEOMETRY_ROWS` переезжает сюда из `BlockEconomicsPage.tsx` (там удаляется в задаче 3).

- [ ] **Step 1: Написать падающий тест**

```ts
import { describe, expect, it } from "vitest";

import { passportMetrics, passportRows } from "./passportSummary";

/** Неразрывный пробел тысяч — обычным, чтобы ожидание читалось глазами. */
const plain = (text: string) => text.replace(/\u00a0/g, " ");

const PHYSICAL = {
  rock_volume_m3: 30000,
  drilling_m: "2420",
  holes: 220,
  explosive_kg: 29554.55,
  downhole_nsi: 220,
  surface_nsi: 220,
};

describe("плашки паспорта", () => {
  it("четыре показателя в порядке чтения", () => {
    const shown = passportMetrics(PHYSICAL).map((m) => `${m.label}: ${plain(m.value)} ${m.unit}`);

    expect(shown).toEqual([
      "Объём блока: 30 000 м³",
      "Погонаж бурения: 2 420 п.м.",
      "Скважины: 220 шт",
      "С одной скважины: 11,0 м",
    ]);
  });

  it("выход с одной скважины — погонаж на число скважин, с одним знаком", () => {
    expect(passportMetrics({ drilling_m: 2500, holes: 220 })[3].value).toBe("11,4");
  });

  it("без скважин выход — прочерк, а не бесконечность", () => {
    expect(passportMetrics({ drilling_m: 2420, holes: 0 })[3].value).toBe("—");
    expect(passportMetrics({ drilling_m: 2420 })[3].value).toBe("—");
  });

  it("отсутствующая величина — прочерк", () => {
    expect(passportMetrics({})[0].value).toBe("—");
  });
});

describe("полная таблица паспорта", () => {
  it("показывает только посчитанные величины, источник — из lineage или «технический расчёт»", () => {
    const rows = passportRows(
      { rock_volume_m3: 30000, holes: 220 },
      { holes: "BlastGeometry.block.total_holes" },
    );

    expect(rows.map((row) => row.key)).toEqual(["rock_volume_m3", "holes"]);
    expect(plain(rows[0].value)).toBe("30 000");
    expect(rows[0].source).toBe("технический расчёт");
    expect(rows[1].source).toBe("BlastGeometry.block.total_holes");
  });
});
```

- [ ] **Step 2: Запустить и убедиться, что падает**

Run: `cd frontend && npx vitest run src/pages/economics/passportSummary.test.ts`
Expected: FAIL — модуль `./passportSummary` не найден.

- [ ] **Step 3: Реализовать модуль**

```ts
import { amount } from "./format";
import type { Numeric } from "../../types/blockEconomics";

/**
 * Что из паспорта видно на вкладке «Экономика блока»: четыре плашки над
 * сметой и полная таблица под раскрывашкой. Геометрию посчитал технический
 * паспорт, здесь её только показывают.
 */

/** Показатель плашки: подпись, значение русской записью, единица. */
export type PassportMetric = { key: string; label: string; value: string; unit: string };

/** Строка полной таблицы: то же плюс источник величины в паспорте. */
export type PassportRow = PassportMetric & { source: string };

/** Драйверы паспорта в порядке чтения: ключ `physical`, подпись, единица. */
export const GEOMETRY_ROWS: [string, string, string][] = [
  ["rock_volume_m3", "Объём блока", "м³"],
  ["drilling_m", "Погонаж бурения", "п.м."],
  ["holes", "Скважины", "шт"],
  ["explosive_kg", "Масса ВВ", "кг"],
  ["downhole_nsi", "Скважинные НСИ", "шт"],
  ["surface_nsi", "Поверхностные НСИ", "шт"],
];

const NO_VALUE = "—";
const TECHNICAL_SOURCE = "технический расчёт";

/** Величина паспорта числом; пусто или не число — null, не NaN. */
function numberOf(physical: Record<string, Numeric>, key: string): number | null {
  const raw = physical[key];
  if (raw === undefined || raw === null || raw === "") return null;
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
}

const shown = (value: number | null) => (value === null ? NO_VALUE : amount(value));

/**
 * Четыре плашки полосы паспорта. Выход метров с одной скважины паспорт не
 * хранит — это погонаж на число скважин; без скважин показывать нечего:
 * прочерк, а не Infinity.
 */
export function passportMetrics(physical: Record<string, Numeric>): PassportMetric[] {
  const drilling = numberOf(physical, "drilling_m");
  const holes = numberOf(physical, "holes");
  const perHole = drilling !== null && holes !== null && holes > 0 ? drilling / holes : null;
  return [
    { key: "rock_volume_m3", label: "Объём блока", value: shown(numberOf(physical, "rock_volume_m3")), unit: "м³" },
    { key: "drilling_m", label: "Погонаж бурения", value: shown(drilling), unit: "п.м." },
    { key: "holes", label: "Скважины", value: shown(holes), unit: "шт" },
    {
      key: "meters_per_hole",
      label: "С одной скважины",
      value:
        perHole === null
          ? NO_VALUE
          : perHole.toLocaleString("ru-RU", { minimumFractionDigits: 1, maximumFractionDigits: 1 }),
      unit: "м",
    },
  ];
}

/** Полная таблица паспорта: только те величины, которые паспорт посчитал. */
export function passportRows(
  physical: Record<string, Numeric>,
  lineage: Record<string, string>,
): PassportRow[] {
  return GEOMETRY_ROWS.filter(([key]) => physical[key] !== undefined).map(([key, label, unit]) => ({
    key,
    label,
    unit,
    value: shown(numberOf(physical, key)),
    source: lineage[key] ?? TECHNICAL_SOURCE,
  }));
}
```

- [ ] **Step 4: Запустить тесты**

Run: `cd frontend && npx vitest run src/pages/economics/passportSummary.test.ts`
Expected: PASS (5 тестов).

- [ ] **Step 5: Коммит**

```bash
git add frontend/src/pages/economics/passportSummary.ts frontend/src/pages/economics/passportSummary.test.ts
git commit -m "feat(economics): плашки паспорта и выход метров с одной скважины"
```

---

### Task 3: Полоса паспорта под шапкой

**Files:**
- Create: `frontend/src/pages/economics/PassportStrip.tsx`
- Modify: `frontend/src/pages/economics/BlockEconomicsPage.tsx` (константа `GEOMETRY_ROWS`, ветка `return` с разметкой)
- Modify: `frontend/src/styles.css` (блок «Экономика блока»: `.block-economics-page`, `.block-economics-passport`, `.geometry-readonly`; медиазапросы `max-width:1050px` и `max-width:760px`)

**Interfaces:**
- Consumes: `passportMetrics`, `passportRows` из `./passportSummary`; `TechnicalPassport` из `../../types/blockEconomics`.
- Produces: компонент `PassportStrip` с пропсами

```ts
{
  /** React 19: ref — обычный проп функционального компонента, forwardRef не нужен. */
  ref?: Ref<HTMLDivElement>;
  passports: TechnicalPassport[];
  selectedId: string;
  onSelect: (id: string) => void;
  /** Паспорт, по которому считается модель; null — ещё не загружен. */
  passport: TechnicalPassport | null;
  siteLabel: string;
  revisionLabel: string;
  runName: string;
  runPlaceholder: string;
  onRunName: (name: string) => void;
  onSave: () => void;
  saveDisabled: boolean;
  /** Сообщение о сохранении или переносе услуги; пусто — не показывать. */
  status: string;
}
```

Полоса живёт вне `.page-content`, чтобы примыкать к шапке без полей страницы (как `.workspace-bar` на других вкладках, но без своей рамки). Статус сохранения переезжает из `.page-heading` в ряд плашек справа: там ему хватает ширины и для длинного сообщения о переносе услуги.

- [ ] **Step 1: Создать `PassportStrip.tsx`**

```tsx
import type { Ref } from "react";
import { passportMetrics, passportRows } from "./passportSummary";
import type { TechnicalPassport } from "../../types/blockEconomics";

/**
 * Полоса паспорта под шапкой приложения: объект, паспорт, ревизия, имя
 * сценария и «Сохранить сценарий» одной строкой; ниже — четыре плашки
 * геометрии, а остальные величины паспорта с источниками — под
 * раскрывашкой. Полоса закреплена при прокрутке (`.passport-strip` в
 * styles.css), поэтому страница меряет её высоту через `ref` и на неё
 * отступает липкую колонку параметров.
 */
export function PassportStrip({
  ref,
  passports,
  selectedId,
  onSelect,
  passport,
  siteLabel,
  revisionLabel,
  runName,
  runPlaceholder,
  onRunName,
  onSave,
  saveDisabled,
  status,
}: {
  /** React 19: ref — обычный проп функционального компонента, forwardRef не нужен. */
  ref?: Ref<HTMLDivElement>;
  passports: TechnicalPassport[];
  selectedId: string;
  onSelect: (id: string) => void;
  /** Паспорт, по которому считается модель; null — ещё не загружен. */
  passport: TechnicalPassport | null;
  siteLabel: string;
  revisionLabel: string;
  runName: string;
  runPlaceholder: string;
  onRunName: (name: string) => void;
  onSave: () => void;
  saveDisabled: boolean;
  /** Сообщение о сохранении или переносе услуги; пусто — не показывать. */
  status: string;
}) {
  return (
    <div className="passport-strip" ref={ref}>
      <div className="passport-strip-fields">
        <label>
          Объект работ
          <input value={siteLabel} title={passport?.site_code ?? ""} disabled />
        </label>
        <label>
          Технический паспорт
          <select value={selectedId} onChange={(event) => onSelect(event.target.value)}>
            {passports.map((item) => (
              <option key={item.id} value={item.id}>
                {item.object_name} · вер. {item.version_no}
              </option>
            ))}
          </select>
        </label>
        <label>
          Ревизия справочников
          <input value={revisionLabel} title={passport?.reference_revision_id ?? ""} disabled />
        </label>
        <label>
          Имя сценария
          <input
            value={runName}
            placeholder={runPlaceholder}
            onChange={(event) => onRunName(event.target.value)}
          />
        </label>
        <div className="passport-strip-actions">
          <button type="button" onClick={onSave} disabled={saveDisabled}>
            Сохранить сценарий
          </button>
        </div>
      </div>
      {passport && (
        <>
          <div className="passport-strip-metrics">
            {passportMetrics(passport.physical).map((metric) => (
              <div className="metric-chip" key={metric.key}>
                <span>{metric.label}</span>
                <strong>{metric.value}</strong>
                <small>{metric.unit}</small>
              </div>
            ))}
            {status && <span className="save-status">{status}</span>}
          </div>
          <details className="passport-strip-details">
            <summary>Все показатели паспорта и источники</summary>
            <div className="table-scroll geometry-readonly">
              <table>
                <thead>
                  <tr><th>Показатель</th><th>Значение</th><th>Ед.</th><th>Источник</th></tr>
                </thead>
                <tbody>
                  {passportRows(passport.physical, passport.lineage).map((row) => (
                    <tr key={row.key}>
                      <td>{row.label}</td>
                      <td>{row.value}</td>
                      <td>{row.unit}</td>
                      <td><small>{row.source}</small></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Подключить полосу на странице**

В `BlockEconomicsPage.tsx`:

1. Удалить константу `GEOMETRY_ROWS` и комментарий над ней (переехали в `passportSummary.ts`).
2. Добавить импорт `import { PassportStrip } from "./PassportStrip";`.
3. Заменить основной `return` (от `<div className="page-content block-economics-page">` до конца) на:

```tsx
return (
  <div className="block-economics-page">
    <PassportStrip
      passports={passports}
      selectedId={selectedPassport}
      onSelect={setSelectedPassport}
      passport={passport}
      siteLabel={siteLabel}
      revisionLabel={revisionLabel}
      runName={runName}
      runPlaceholder={`Сценарий ${runs.length + 1}`}
      onRunName={setRunName}
      onSave={() => void saveRun()}
      saveDisabled={busy || !activeEconomics}
      status={status}
    />
    <div className="page-content block-economics-content">
      <EconomicsHelp />
      {error && <div className="page-error" role="alert">{error}</div>}

      <div className="block-economics-grid">
        {defaults && activeVariant && (
          <div className="block-economics-inputs">
            <VariantTabs
              variants={variants}
              activeId={activeId}
              onSelect={selectVariant}
              onDuplicate={handleDuplicateVariant}
              onRemove={handleRemoveVariant}
              onRename={handleRenameVariant}
            />
            <NomenclaturePanel params={activeVariant.parameters} defaults={defaults} onChange={patchActive} />
            <ParametersPanel
              params={activeVariant.parameters}
              defaults={defaults}
              computedRevisionId={activeEconomics?.reference_revision_id}
              onChange={patchActive}
            />
            <ServicesPanel
              services={activeVariant.parameters.services}
              operations={defaults.operations}
              canEdit={canEdit}
              busyCode={movingService}
              onChange={(services) => patchActive({ services })}
              onMove={(index) => void moveServiceToReference(index)}
            />
          </div>
        )}
        <div className="block-economics-results">
          {results.length > 0 && activeEconomics ? (
            <>
              <PricePanel economics={activeEconomics} />
              <ModelWarnings economics={activeEconomics} />
              <DrillingBreakdown economics={activeEconomics} />
              <CostStructure results={results} />
            </>
          ) : (
            <div className="economic-empty">Расчёт выполняется…</div>
          )}
        </div>
      </div>

      <SensitivityTable rows={sensitivity} busy={sensitivityBusy} onCompute={() => void computeSensitivity()} />

      <RunsCompare
        runs={runs}
        selected={selectedRuns}
        compare={compare}
        busy={busy}
        onToggle={(runId) =>
          setSelectedRuns((current) =>
            current.includes(runId)
              ? current.filter((item) => item !== runId)
              : current.length >= 3
                ? current
                : [...current, runId],
          )
        }
        onCompare={() => void compareRuns()}
      />
    </div>
  </div>
);
```

Ветка «паспортов нет» (`if (!selectedPassport)`) не меняется. `EconomicsHelp` остаётся: его `h2.sr-only` — имя страницы для программ чтения, кнопка уходит порталом в слот шапки.

- [ ] **Step 3: Стили полосы**

В `styles.css` в блоке «Экономика блока»:

Заменить `.block-economics-page { display:grid; gap:16px; }` на `.block-economics-content { display:grid; gap:16px; }`.

Удалить две строки:

```css
.block-economics-passport .economic-fields-grid { padding-bottom:4px; }
.block-economics-passport .button-row { align-self:end; }
```

Заменить `.geometry-readonly { margin-top:12px; }` на `.geometry-readonly { margin-top:8px; }` (остальные два правила `.geometry-readonly` оставить).

Перед `.block-economics-content` добавить:

```css
/* --- Полоса паспорта под шапкой (см. PassportStrip.tsx): поля одной строкой,
   ниже плашки геометрии тем же видом, что на листе «Расчёт» (.metric-chip),
   остальные величины паспорта — под раскрывашкой. Вне .page-content, чтобы
   примыкать к шапке без полей страницы. --- */
.passport-strip { padding:12px 28px; border-bottom:1px solid #dce4e0; background:#fff; }
.passport-strip-fields { display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1.25fr) minmax(0,1fr) minmax(0,1fr) auto; gap:11px; align-items:end; }
.passport-strip-fields label { display:grid; gap:6px; min-width:0; color:#425149; font-size:11px; font-weight:700; }
.passport-strip-fields input, .passport-strip-fields select { width:100%; min-width:0; padding:8px 9px; border:1px solid #cfd9d4; border-radius:8px; background:#fbfcfb; }
.passport-strip-actions button { padding:9px 13px; border:1px solid #cfd9d4; border-radius:9px; background:#fff; font-size:12px; font-weight:700; color:#3b4b43; white-space:nowrap; }
.passport-strip-actions button:disabled { opacity:.5; cursor:not-allowed; }
.passport-strip-metrics { display:flex; flex-wrap:wrap; align-items:center; gap:8px; margin-top:10px; }
/* Статус сохранения справа от плашек: длинному сообщению о переносе услуги
   здесь хватает ширины, в ряду с кнопкой — нет. */
.passport-strip-metrics .save-status { margin-left:auto; }
.passport-strip-details { margin-top:8px; font-size:12px; }
.passport-strip-details summary { cursor:pointer; color:#31483d; font-weight:700; }
```

В медиазапрос `@media (max-width:1050px)` рядом с `.block-economics-grid { grid-template-columns:1fr; }` добавить:

```css
.passport-strip-fields { grid-template-columns:repeat(2,minmax(0,1fr)); }
.passport-strip-actions { grid-column:1 / -1; }
```

В медиазапрос `@media (max-width:760px)` рядом с `.cost-structure-head` добавить:

```css
.passport-strip { padding:10px 14px; }
.passport-strip-fields { grid-template-columns:1fr; }
```

- [ ] **Step 4: Сборка и тесты**

Run: `cd frontend && npm run build && npx vitest run`
Expected: сборка без ошибок (в том числе нет неиспользуемых импортов в `BlockEconomicsPage.tsx`), все тесты PASS.

- [ ] **Step 5: Проверить в браузере**

На вкладке «Экономика»: под шапкой полоса — Объект · Паспорт · Ревизия · Имя сценария · кнопка в одну строку; ниже четыре плашки, у «С одной скважины» — погонаж ÷ скважины (для демо-блока 2 420 / 220 = 11,0 м). Раскрывашка показывает шесть строк с источниками. «Сохранить сценарий» — статус появляется справа от плашек. Сменить паспорт в селекте — плашки обновляются.

- [ ] **Step 6: Коммит**

```bash
git add frontend/src/pages/economics/PassportStrip.tsx frontend/src/pages/economics/BlockEconomicsPage.tsx frontend/src/styles.css
git commit -m "feat(economics): полоса паспорта под шапкой — поля одной строкой и плашки геометрии"
```

---

### Task 4: Полоса закреплена при прокрутке

**Files:**
- Create: `frontend/src/lib/useElementHeight.ts`
- Modify: `frontend/src/pages/economics/BlockEconomicsPage.tsx` (импорты, хук, корневой `div` и проп `ref` у `PassportStrip`)
- Modify: `frontend/src/styles.css` (`.passport-strip`, `.block-economics-inputs`, медиазапрос `max-width:760px`)

**Interfaces:**
- Produces: `useElementHeight(): [ref: (node: HTMLElement | null) => void, height: number]` — callback-ref и высота узла в px, до монтирования 0.
- Consumes: проп `ref` у `PassportStrip` из задачи 3.

Шапка приложения не липкая, поэтому полоса с `top:0` прилипает к краю окна, когда шапка уезжает. Колонка параметров уже липкая (`top:14px`) — без отступа на высоту полосы она заезжала бы под неё. Высота полосы меняется (перенос полей, открытая раскрывашка), поэтому её меряет `ResizeObserver`, а не константа в CSS.

- [ ] **Step 1: Хук высоты**

```ts
import { useCallback, useState, type RefCallback } from "react";

/**
 * Высота DOM-узла в пикселях, обновляемая `ResizeObserver`-ом: для липких
 * блоков, которым надо отступить на высоту другого липкого блока над ними.
 * Возвращает callback-ref (узел может смонтироваться позже хука) и текущую
 * высоту; до монтирования — 0. React 19 вызывает функцию очистки,
 * возвращённую из ref, при размонтировании узла.
 */
export function useElementHeight(): [RefCallback<HTMLElement>, number] {
  const [height, setHeight] = useState(0);
  const ref = useCallback((node: HTMLElement | null) => {
    if (!node) return;
    setHeight(node.offsetHeight);
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => setHeight(node.offsetHeight));
    observer.observe(node);
    return () => {
      observer.disconnect();
      setHeight(0);
    };
  }, []);
  return [ref, height];
}
```

- [ ] **Step 2: Передать высоту в CSS**

В `BlockEconomicsPage.tsx`:

1. Импорты: `import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";` и `import { useElementHeight } from "../../lib/useElementHeight";`.
2. Рядом с остальными хуками состояния: `const [stripRef, stripHeight] = useElementHeight();`.
3. Корневой `div` основного `return`:

```tsx
<div
  className="block-economics-page"
  // Липкая колонка параметров отступает на высоту липкой полосы — см. .block-economics-inputs.
  style={{ "--passport-strip-h": `${stripHeight}px` } as CSSProperties}
>
  <PassportStrip
    ref={stripRef}
    ...
```

- [ ] **Step 3: Стили липкости**

В `styles.css`: `.passport-strip { padding:12px 28px; ... }` → добавить в начало правила `position:sticky; top:0; z-index:5;`:

```css
.passport-strip { position:sticky; top:0; z-index:5; padding:12px 28px; border-bottom:1px solid #dce4e0; background:#fff; }
```

`.block-economics-inputs { display:grid; gap:16px; align-content:start; position:sticky; top:14px; }` → 

```css
/* Отступ на высоту липкой полосы паспорта над колонкой: переменную ставит
   BlockEconomicsPage по ResizeObserver, без полосы — обычные 14px. */
.block-economics-inputs { display:grid; gap:16px; align-content:start; position:sticky; top:calc(var(--passport-strip-h, 0px) + 14px); }
```

В медиазапрос `@media (max-width:760px)` к `.passport-strip { padding:10px 14px; }` добавить `position:static;` — на телефоне полоса в три строки съела бы экран.

- [ ] **Step 4: Сборка и тесты**

Run: `cd frontend && npm run build && npx vitest run`
Expected: PASS.

- [ ] **Step 5: Проверить в браузере**

На вкладке «Экономика» прокрутить до сметы: полоса прилипла к верху окна, колонка параметров начинается сразу под ней, а не под полосой. Открыть раскрывашку — полоса выросла, колонка сдвинулась вниз; закрыть — вернулась. `getComputedStyle(document.querySelector(".block-economics-inputs")).top` равен высоте полосы + 14px. Диалог «Справка» открывается поверх полосы. Сделать скриншот вкладки и показать пользователю.

- [ ] **Step 6: Коммит**

```bash
git add frontend/src/lib/useElementHeight.ts frontend/src/pages/economics/BlockEconomicsPage.tsx frontend/src/styles.css
git commit -m "feat(economics): полоса паспорта закреплена при прокрутке, колонка параметров отступает на её высоту"
```

---

### Task 5: Завершение ветки

- [ ] **Step 1: Полная проверка**

Run: `cd frontend && npm run build && npx vitest run`; `git status` — в коммитах только файлы из плана, чужие незакоммиченные правки на месте.

- [ ] **Step 2: Ревью и PR**

По правилу проекта (память `review-before-merge`) — сначала `/code-review` по ветке, затем PR `feat/block-economics-header` → `feat/block-economics-variants` (или → `main`, если варианты уже слиты) с описанием: одна строка шапки на всех вкладках, полоса паспорта с плашками, выход метров с одной скважины, липкость.

---

## Чего этот план намеренно не делает

**Не переносит полосу паспорта в шапку порталом**, как полосу листа «Расчёт»: пять полей и четыре плашки в одной строке с заголовком и брендом не помещаются, а шапка по решению — один ряд.

**Не убирает данные паспорта**: Масса ВВ и НСИ нужны реже и уходят под раскрывашку, но остаются на вкладке вместе с источниками.

**Не делает шапку липкой**: страницы длинные, а прилипает то, что нужно при чтении сметы — паспорт и параметры; заголовок и «Выйти» при прокрутке не нужны.
