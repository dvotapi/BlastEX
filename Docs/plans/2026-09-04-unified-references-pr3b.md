# Единые справочники, PR 3b: выгрузка в public при публикации, зеркала разделов, права

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Опубликованные в BlastEX объекты, контрагенты, техника, СИ и буровой инструмент появляются в таблицах журнала `public` той же транзакцией, что и ревизия; разделы без аналога в журнале администратор может зеркалить в `public.blastex_<section>`; администратор базы получает скрипт прав для роли `blastex`.

**Architecture:** Пакет `cost/v2/public_sync/` дополняется тремя модулями: `push.py` строит план записей в `public` (вставки, обновления, новые связи) из опубликованных разделов и связей — чистая функция; `writer.py` исполняет план SQL-командами внутри сессии публикации; `mirror.py` создаёт и обновляет таблицы-зеркала по JSON-схемам разделов. `PostgresEconomicsRepository.publish_references` вызывает их после записи ревизии и связей, в той же транзакции. Обмен и зеркала включаются настройками организации (переключатели хранятся в существующей таблице `public_mirror_sections`), поэтому на VPS до выдачи прав публикация продолжает работать.

**Tech Stack:** Python 3.12, SQLAlchemy 2 (`text()`), PostgreSQL 16 (RLS, `CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`), FastAPI, Pydantic 2; React 19 + TypeScript + vitest; pytest с живой базой (`tests/pg_public.py`).

**Spec:** `Docs/specs/2026-09-03-unified-references-design.md` — §4.5 (выгрузка), §5 (зеркала), §10 (права), §11 (тесты обмена и зеркал), §14 (риски), §12 пункт 4.

## Global Constraints

- Ветка `feat/public-exchange-push` от `main` (после слияния PR 52).
- Выгрузка выполняется внутри транзакции публикации: либо ревизия, связи и записи в `public` записаны все, либо ничего (§3, §4.5 п. 4). Любая ошибка записи в `public` → откат и `HTTP 502` с текстом «Не удалось записать в project1.public: …».
- В `public` никогда не выполняется `DELETE`; деактивация — `is_active = false`; `status` единиц техники приложение не меняет (§3, §4.1).
- Порядок записи: контрагенты → объекты → типы машин и модели → единицы → материалы СИ → материалы инструмент (§4.5 п. 2). Цены и материалы других видов в `public` не выгружаются.
- Обновляются только общие поля (`shared_fields` разделов из `cost/v2/public_sync/mapping.py`) и только при различии; совпадающие строки не трогаются (§4.5 п. 1).
- Ограничения `public` проверяются валидацией до транзакции, текст называет раздел, код и причину (§4.5 п. 3): ИНН по `^[0-9]{10}([0-9]{2})?$`, объект без заказчика и без «заказчика текстом», основное средство без типа, `short_name` объекта длиннее 5, повтор `model_name` среди типов техники.
- Выгрузка и зеркала включаются настройками организации (переключатели в `blastex.public_mirror_sections`: ключ `_exchange` — обмен с существующими таблицами, ключ раздела — зеркало); по умолчанию всё выключено, публикация без прав на `public` продолжает работать. Ruling контроллера: спецификация §4.5 описывает выгрузку безусловной; переключатель добавлен, чтобы не заблокировать публикацию на VPS до выдачи прав; §4.5 и §10 дополняются одной фразой.
- Зеркала (§5): таблица `public.blastex_<section>`, фиксированные колонки `code text primary key`, `name text not null`, `is_active boolean not null`, `valid_from date`, `valid_to date`, `revision_id varchar(36) not null`, `synced_at timestamptz not null`; колонки по полям схемы: `Decimal → numeric`, `bool → boolean`, `str`/`Literal`/ссылка → `text`, `date → date`, списки и вложенные модели → `jsonb`; `x-internal` не выгружаются; комментарий колонки — `title` или `description`; при включении — `CREATE TABLE IF NOT EXISTS`, `ENABLE ROW LEVEL SECURITY`, политика полного доступа роли `blastex`; новое поле схемы → `ADD COLUMN IF NOT EXISTS`; колонки не удаляются и не переименовываются; при публикации строки upsert по `code`, отсутствующие в ревизии → `is_active = false`.
- Скрипт `scripts/grant_public_access.sql` покрывает все таблицы `cost.v2.public_sync.mapping.TABLES` (13 таблиц, включая `machine_types`, `delay_series`, `contracts`, `tools_inventory`) и последовательности, `USAGE, CREATE` на схему `public`, политики RLS полного доступа для роли `blastex`; приложение прав не меняет (§10).
- Каждый метод `PostgresEconomicsRepository` без подчёркивания принимает `organization_id` первым аргументом.
- Тесты с PostgreSQL — через `tests/pg_public.py` (`requires_pg`, `public_db`, `seed_public`, база `project1_test`, URL из `.claude/launch.json` с заменой имени базы; никогда не `project1`). Docker должен быть запущен: проверить `docker info` в начале.
- Тексты, комментарии, коммиты — на русском; коммиты завершаются `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`; в `git add` только файлы задачи (посторонние untracked-файлы с суффиксами « 2»/« 3» не трогать; типы фронта проверять временным tsconfig с `exclude`).
- Python-тесты: `.venv/bin/python -m pytest -q` (плюс прогон с `BLASTEX_TEST_DATABASE_URL`); фронт: `cd frontend && npm test`.

---

## Структура файлов

| Файл | Ответственность |
|---|---|
| `cost/v2/public_sync/push.py` (создать) | план записей в `public` по опубликованным разделам и связям; валидация ограничений `public` |
| `cost/v2/public_sync/writer.py` (создать) | исполнение плана SQL внутри сессии; `PublicWriteError` |
| `cost/v2/public_sync/mirror.py` (создать) | DDL и upsert зеркал по JSON-схеме раздела |
| `cost/v2/public_sync/settings.py` (создать) | ключ `_exchange`, `PublicSyncSettings`, разделы, доступные для зеркал |
| `cost/v2/repository.py`, `cost/v2/db_repository.py` (изменить) | публикация вызывает выгрузку и зеркала; методы настроек |
| `cost/v2/references.py` (без изменений) | валидация справочников; ограничения `public` — отдельная функция в `push.py`, вызывается роутером |
| `api/schemas/economics.py`, `api/routers/economics.py`, `api/services/public_sync_service.py` (изменить) | настройки обмена, 502 при ошибке записи, валидация ограничений при включённом обмене |
| `api/security.py` (изменить) | `require_admin` |
| `frontend/src/pages/references/PublicSyncSettings.tsx` (создать), `ReferencesPage.tsx`, `endpoints.ts`, `types/economics.ts` (изменить) | панель настроек обмена и зеркал (только администратор) |
| `scripts/grant_public_access.sql` (создать), `README.md`, спецификация §4.5/§10 (изменить) | права и документация |
| `tests/test_public_sync_push.py`, `test_public_sync_mirror.py`, `test_public_sync_push_pg.py`, `test_public_sync_mirror_pg.py`, `test_api_public_settings.py` (создать); `test_api_economics.py`, `test_repository_organization_isolation.py` (изменить) | тесты |

---

### Task 0: Ветка и спецификация

- [ ] `git checkout main && git pull -q origin main && git checkout -b feat/public-exchange-push`.
- [ ] В спецификации §4.5 перед пунктом 1 добавить абзац: «Выгрузка выполняется, если администратор включил обмен для организации (настройка «Выгружать записи в project1.public»); до выдачи прав роли `blastex` обмен выключен, публикация работает как раньше». В §10 после первого абзаца: «Пока скрипт не выполнен, обмен и зеркала остаются выключенными; при попытке включить их без прав интерфейс показывает текст ошибки базы».
- [ ] Коммит `docs(specs): обмен с public включается настройкой организации`.

---

### Task 1: Настройки обмена в репозитории

**Files:** `cost/v2/public_sync/settings.py` (создать), `cost/v2/repository.py`, `cost/v2/db_repository.py`, `tests/test_repository_organization_isolation.py`.

**Interfaces:**

```python
# cost/v2/public_sync/settings.py
EXCHANGE_KEY = "_exchange"                       # ключ переключателя обмена в public_mirror_sections
MAPPED_SECTIONS = ("counterparties", "sites", "equipment_types", "equipment_assets", "materials")

@dataclass(frozen=True)
class PublicSyncSettings:
    exchange_enabled: bool
    mirror_sections: frozenset[str]              # включённые зеркала (без EXCHANGE_KEY)

def mirrorable_sections() -> tuple[str, ...]     # разделы со схемой, не входящие в MAPPED_SECTIONS, без deprecated
def settings_from_flags(flags: Mapping[str, bool]) -> PublicSyncSettings
```

Репозиторий: `get_public_sync_settings(organization_id) -> PublicSyncSettings` (читает `list_mirror_sections` и переводит через `settings_from_flags`) и `set_public_sync_settings(organization_id, user_id, settings) -> PublicSyncSettings` (пишет `set_mirror_section` для `_exchange` и каждого раздела из `mirrorable_sections()`; неизвестный раздел → `EconomicsRepositoryError`). Реализация в протоколе, in-memory и PostgreSQL (последний может делегировать существующим методам). Тесты: изоляция организаций, round-trip, отказ для раздела из `MAPPED_SECTIONS`.

- [ ] Тесты → падают → реализация → `pytest tests/test_repository_organization_isolation.py tests/test_cost_v2_repository.py -q` → коммит `feat(repository): настройки обмена со схемой public`.

---

### Task 2: План выгрузки и валидация ограничений public

**Files:** `cost/v2/public_sync/push.py` (создать), `tests/test_public_sync_push.py`.

**Interfaces:**

```python
@dataclass(frozen=True)
class PublicInsert:
    table: str
    values: dict[str, Any]          # колонки public
    section: str
    code: str                       # запись blastex, для связи после RETURNING id
    depends_on: tuple[tuple[str, str], ...] = ()   # (table, code) родителей, чьи id подставляются writer'ом: ("counterparties", code) для client_legal_name не нужен (текст), ("equipment_models", code) для units.model_id, ("machine_types", name) для models.machine_type_id

@dataclass(frozen=True)
class PublicUpdate:
    table: str
    public_id: int
    values: dict[str, Any]          # только изменившиеся общие поля

@dataclass(frozen=True)
class PublicWritePlan:
    inserts: tuple[PublicInsert, ...]
    updates: tuple[PublicUpdate, ...]
    def is_empty(self) -> bool

def public_constraint_issues(
    sections: Mapping[str, Sequence[ReferenceItem]],
    links: Sequence[PublicLink],
) -> list[ValidationIssue]

def plan_public_writes(
    sections: Mapping[str, Sequence[ReferenceItem]],
    links: Sequence[PublicLink],
    snapshot: PublicSnapshot,
) -> PublicWritePlan
```

Правила `plan_public_writes` (обратное сопоставление §4.1, только общие поля):
- `counterparties`: `full_name ← name`, `short_name ← short_name`, `inn ← inn`, `is_client`/`is_supplier` только поднимаются (`CUSTOMER` → `is_client=true`; `SUPPLIER`/`SUBCONTRACTOR` → `is_supplier=true`; существующие `true` не сбрасываются), `is_active`; при вставке `is_client`/`is_supplier` по роли.
- `sites`: `full_name ← name`, `short_name`, `mineral_type`, `is_active`, `client_legal_name ← short_name или name контрагента по customer_code, иначе customer_legal_name`.
- `equipment_types` → `equipment_models`: `model_name ← name`, `brand ← brand or ""` (колонка NOT NULL: пустая строка), `machine_type_id` ← строка `machine_types` по `machine_type_name` (создаётся `PublicInsert("machine_types", {"name": ...})`, если нет; при пустом `machine_type_name` берётся русская подпись `kind` из словаря `MACHINE_KINDS` в обратную сторону, для `OTHER` — «Прочая техника»).
- `equipment_assets` → `equipment_units`: `internal_id ← inventory_number or code`, `serial_number`, `model_id` по связи типа; `status` не трогать; при вставке `status = 'В работе'` если `is_active`, иначе `'Списано'`; при обновлении неактивной записи — `status` не меняем (журнал главный), но это фиксируется предупреждением в плане (поле `warnings` у `PublicWritePlan`).
- `materials` с `material_kind == "СИ"` → `initiating_device_types`: `name`, `description ← comment`; с `material_kind == "Буровой инструмент"` → `tool_types`: `name`, `description ← comment`, `expected_lifetime_meters ← lifetime_m`, `diameter ← diameter_mm`, `thread_type`.
- Записи со связью: сравнить общие поля с текущей строкой `snapshot` (нормализация как в `delta.py`: `_comparable`); различие → `PublicUpdate` только с изменёнными колонками; связь есть, а строки в `snapshot` нет → предупреждение, запись пропускается.
- Записи без связи: `PublicInsert`; неактивные записи без связи не вставляются.
- Зависимости: вставки упорядочены (контрагенты, объекты, типы машин, модели, единицы, СИ, инструмент); `writer` подставляет `id` родителей по `(table, code)` из только что вставленных строк или из связей.

`public_constraint_issues` (только когда обмен включён — решает роутер): ошибки уровня `error` с `section`, `code`, полем: ИНН пуст или не по формату (`field="inn"`), объект без заказчика (`field="customer_code"`), `short_name` длиннее 5 (`field="short_name"`), основное средство без типа или с типом, которого нет в разделе (`field="equipment_type_code"`), повтор `name` среди активных типов техники (`model_name` уникален в `public`).

Тесты (без базы): планы на выборке из `seed_public`-подобного снимка и разделов: вставка нового контрагента и объекта с `client_legal_name` из краткого имени; обновление только изменённого `short_name`; неизменённая запись → ни вставки, ни обновления; флаги `is_client/is_supplier` не сбрасываются; единица без связи типа → `depends_on` на модель; валидация: все пять ошибок с правильными `field`.

- [ ] Тесты → падают → реализация → коммит `feat(public-sync): план выгрузки в public и проверка ограничений журнала`.

---

### Task 3: Исполнение плана и хук в публикацию

**Files:** `cost/v2/public_sync/writer.py` (создать), `cost/v2/db_repository.py`, `cost/v2/repository.py` (in-memory: план считается, но не исполняется — `InMemoryEconomicsRepository` хранит «выгруженное» в `self._public_writes` для тестов API), `tests/test_public_sync_push_pg.py`, `tests/test_cost_v2_repository.py`.

**Interfaces:**

```python
class PublicWriteError(RuntimeError): ...       # текст: «Не удалось записать в project1.public: <причина>»

class SqlPublicWriter:
    def __init__(self, session: Session) -> None
    def apply(self, plan: PublicWritePlan) -> list[PublicLink]   # выполняет вставки (INSERT ... RETURNING id) и обновления; возвращает новые связи для записей blastex
```

Хук: в `PostgresEconomicsRepository.publish_references` после записи ревизии и связей — если `get_public_sync_settings(...).exchange_enabled`: прочитать `public` (`SqlPublicReader` на той же сессии/connection — добавить конструктор от `Connection`), построить план, выполнить `SqlPublicWriter(session).apply(plan)`, записать новые связи через `_upsert_public_link`, добавить в `AuditLogRow.after_payload` сводку `{"public_writes": {"inserted": n, "updated": m}}`. Ошибки SQL → `PublicWriteError` → транзакция откатывается. `_ensure_defaults` и остальной код не меняются.

pg-тесты (`tests/test_public_sync_push_pg.py`, `requires_pg`, `public_db`, `seed_public`): включить обмен; опубликовать ревизию с новым контрагентом (ИНН `6685101311`), новым объектом (заказчик — контрагент), типом техники, единицей и материалом СИ → в `public` появились строки, связи записаны, повторная публикация без изменений не меняет `updated_at` строк `public`; публикация с изменённым `short_name` объекта → `UPDATE` одной колонки; искусственная ошибка (например, `model_name` дублирует существующую строку `public` без связи) → `PublicWriteError`, ревизия не создана (`list_reference_revisions` не вырос).

- [ ] Тесты → реализация → `pytest` с `BLASTEX_TEST_DATABASE_URL` → коммит `feat(public-sync): выгрузка в public внутри транзакции публикации`.

---

### Task 4: Зеркала разделов

**Files:** `cost/v2/public_sync/mirror.py` (создать), `cost/v2/db_repository.py`, `tests/test_public_sync_mirror.py`, `tests/test_public_sync_mirror_pg.py`.

**Interfaces:**

```python
@dataclass(frozen=True)
class MirrorColumn:
    name: str
    sql_type: str          # numeric | boolean | text | date | jsonb
    comment: str

def mirror_table_name(section: str) -> str                      # blastex_<section>
def mirror_columns(section: str) -> list[MirrorColumn]          # фиксированные + по схеме, без x-internal
def create_table_sql(section: str) -> list[str]                 # CREATE TABLE IF NOT EXISTS, ALTER ... ADD COLUMN IF NOT EXISTS для каждой колонки схемы, COMMENT ON COLUMN, ENABLE ROW LEVEL SECURITY, CREATE POLICY (через DO $$ ... IF NOT EXISTS (select 1 from pg_policies ...) $$)
def ensure_mirror(session: Session, section: str) -> None
def sync_mirror(session: Session, section: str, revision_id: str, items: Sequence[ReferenceItem], now: datetime) -> tuple[int, int]   # (upserted, deactivated)
```

Значения: `Decimal`/числовые строки → `numeric` (через `Decimal(str(v))`), пустые → `NULL`, списки/объекты → `json.dumps(ensure_ascii=False)::jsonb`, даты → `date`. Хук в `publish_references`: для каждого включённого зеркала — `ensure_mirror` и `sync_mirror` в той же транзакции; ошибки → `PublicWriteError`. Включение зеркала (`set_public_sync_settings`) в PostgreSQL сразу вызывает `ensure_mirror` в отдельной транзакции, чтобы ошибка прав была видна при включении.

Тесты без базы: имена таблиц (`blastex_rocks`), типы колонок для `rocks` (`density_t_m3 numeric`, `fracture_class text`), `crew_templates.members jsonb`, `sites.is_watered boolean`, `legacy_ref` отсутствует, SQL содержит `IF NOT EXISTS` и `ENABLE ROW LEVEL SECURITY`. pg-тесты: включить зеркало `rocks`, опубликовать две породы → таблица есть, две строки; убрать одну и опубликовать → `is_active=false`; добавить в схему поле (monkeypatch `section_json_schema`) → после публикации колонка появилась.

- [ ] Тесты → реализация → коммит `feat(public-sync): зеркала разделов blastex в схеме public`.

---

### Task 5: API настроек и публикации

**Files:** `api/security.py` (`require_admin`: роли `admin`, `service`), `api/schemas/economics.py` (`PublicSyncSettingsSchema(exchange_enabled: bool, mirror_sections: dict[str, bool], mirrorable_sections: list[str], mapped_sections: list[str])`), `api/routers/economics.py` (`GET /references/public-settings` — `require_internal_access`; `PUT /references/public-settings` — `require_admin`; в `publish_references` и `validate_references`: если обмен включён — добавить `public_constraint_issues` к результату валидации; `PublicWriteError` → 502 `{"detail": {"message": ...}}`), `api/services/public_sync_service.py` (сборка ответа настроек), `tests/test_api_public_settings.py`, `tests/test_api_economics.py`.

Тесты: GET по умолчанию — всё выключено, списки разделов; PUT администратором включает обмен и зеркало `rocks`; PUT редактором → 403; PUT с разделом из `MAPPED_SECTIONS` → 422; `validate` при включённом обмене возвращает ошибку ИНН; `publish` с `PublicWriteError` (in-memory репозиторий с подменой) → 502.

- [ ] Тесты → реализация → коммит `feat(api): настройки обмена с public и ошибки выгрузки при публикации`.

---

### Task 6: Панель настроек на странице «Справочники»

**Files:** `frontend/src/types/economics.ts`, `frontend/src/api/endpoints.ts` (`publicSettings()`, `savePublicSettings(payload)`), `frontend/src/pages/references/PublicSyncSettings.tsx` (создать), `ReferencesPage.tsx`, `frontend/src/styles/references.css`.

Панель (только `user.role === "admin"`) сворачиваемая `<details>` рядом с плашкой «Из project1»: переключатель «Обмен с журналом project1.public» и список разделов-зеркал с чекбоксами («Выгружать в project1.public: Породы, Нормативы …»); сохранение сразу по изменению (`PUT`), ошибка базы (нет прав) показывается текстом в панели; после сохранения плашка разницы обновляется. Ошибка публикации 502 показывается в общем `error`. vitest: чистая функция `settingsPatch(current, section, enabled)`; scoped tsc.

- [ ] Коммит `feat(frontend): настройки обмена и зеркал в project1.public`.

---

### Task 7: Скрипт прав и документация

**Files:** `scripts/grant_public_access.sql` (создать), `README.md`, `Docs/specs/…` §10 (ссылка на скрипт).

Скрипт: `GRANT USAGE, CREATE ON SCHEMA public TO blastex;` `GRANT SELECT, INSERT, UPDATE ON <каждая таблица из mapping.TABLES> TO blastex;` `GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO blastex;` для каждой таблицы `CREATE POLICY blastex_full_access ON public.<table> FOR ALL TO blastex USING (true) WITH CHECK (true);` (в `DO $$ … IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE …)`), плюс комментарий, что зеркала `public.blastex_*` создаёт приложение и политику ставит само. Тест `tests/test_grant_script.py`: скрипт упоминает каждую таблицу из `TABLES` и роль `blastex`. README: раздел «Обмен со схемой public» — порядок: выполнить скрипт администратором базы, включить обмен в настройках страницы «Справочники», проверить плашку.

- [ ] Коммит `docs: права роли blastex на схему public и порядок включения обмена`.

---

### Task 8: Проверка на базе и в браузере

- [ ] pg-тесты и полный прогон; dev-база: включить обмен и зеркало «Породы» через UI администратора; опубликовать ревизию с новым объектом и новой породой; в `public`: строка объекта появилась (`select full_name, client_legal_name from public.sites`), таблица `public.blastex_rocks` с породами; повторная публикация без изменений не меняет `updated_at`; плашка «Из project1» после выгрузки пуста. Скриншоты. PR на `main`: «Единые справочники, PR 3b: выгрузка в public при публикации и зеркала разделов».

## Самопроверка плана

- §4.5 п. 1–4 — Task 2/3/5; §5 — Task 4/6; §10 — Task 7 и переключатели (Task 1/5/6); §11 «повторная публикация без изменений не пишет», «порядок внешних ключей», «ошибка откатывает ревизию», «валидация отклоняет контрагента без ИНН и объект без заказчика», зеркала — Task 3/4 pg-тесты.
- Типы: `PublicSyncSettings`/`EXCHANGE_KEY`/`mirrorable_sections` (Task 1) → Task 4/5/6; `PublicWritePlan`/`public_constraint_issues` (Task 2) → Task 3/5; `PublicWriteError` (Task 3) → Task 5; `ensure_mirror`/`sync_mirror` (Task 4) → Task 3 hook и Task 1 (включение).
