# Единые справочники, PR 3a: получение записей из схемы public

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Страница «Справочники» видит записи журнала буровых работ из схемы `public` базы `project1` (объекты, контрагенты, техника, СИ, буровой инструмент, цены СИ и инструмента), показывает разницу с черновиком и по кнопке применяет её в черновик; связь записи blastex с записью `public` хранится в таблице `blastex.public_links`.

**Architecture:** Пакет `cost/v2/public_sync/` не знает об интерфейсе: `mapping.py` описывает сопоставление разделов blastex с таблицами `public` (поля, направления, словари), `reader.py` читает таблицы `public` через тот же движок SQLAlchemy, `delta.py` считает предложения «новая / изменена / деактивирована» относительно черновика с учётом связей. Репозиторий получает таблицу связей и таблицу переключателей зеркал (одна миграция на оба PR 3a/3b). API — два маршрута в `api/routers/economics.py`; фронт — плашка над рабочей областью страницы «Справочники». Выгрузка в `public` при публикации и зеркала разделов — следующий PR 3b.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, SQLAlchemy 2 (`text()` для `public`), Alembic, PostgreSQL 16; React 19 + TypeScript + vitest; pytest.

**Spec:** `Docs/specs/2026-09-03-unified-references-design.md` — §4.1–§4.4 (сопоставление, новые поля, связи, получение), §10 (тестовая база), §11 («Обмен с public»), §13 (факты по данным), §14 (риски). §4.5 (выгрузка) и §5 (зеркала) — PR 3b.

## Global Constraints

- Ветка `feat/public-exchange-pull` от `main`.
- Поля payload описываются только схемами `cost/v2/schemas/`; новые поля для обмена добавляются в схемы, а не в код обмена (спецификация §3, CLAUDE.md).
- Пакет `cost/v2/public_sync/` не знает об интерфейсе; всё для фронта идёт через `api/`.
- Получение из `public` никогда не меняет черновик молча: сервер считает разницу, пользователь применяет её кнопкой и публикует обычным путём (§3). В базу `blastex` из этого PR пишется только таблица связей `public_links`.
- В `public` этот PR ничего не пишет (ни INSERT, ни UPDATE) и никогда не выполняет DELETE.
- Ошибка доступа к `public` (нет прав, нет таблиц, нет схемы) показывается в плашке, остальная страница работает; ответ API в этом случае `200` с `available: false` и текстом ошибки.
- Коды новых записей из `public`: `PUB_<TABLE>_<id>` по §4.3 (`PUB_SITE_12`, `PUB_COUNTERPARTY_5`, `PUB_MODEL_2`, `PUB_UNIT_1`, `PUB_IDT_3`, `PUB_TOOL_4`); коды цен `PRICE_PUB_<источник>_<id>` (`PRICE_PUB_EMP_1`, `PRICE_PUB_SPEC_1`, `PRICE_PUB_TOOL_4`).
- Каждый метод `PostgresEconomicsRepository` без подчёркивания принимает `organization_id` первым аргументом (тест `test_every_repository_method_takes_organization_first`).
- Тесты с PostgreSQL используют `BLASTEX_TEST_DATABASE_URL`, разворачивают `Docs/public_schema.sql` и пропускаются, если переменная не задана (§10). Локально Docker может быть выключен: тесты без базы (сопоставление, разница, API с подменой чтения) обязаны покрывать логику полностью.
- Тексты интерфейса, комментарии, коммиты — на русском; коммиты завершаются `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`; в `git add` только файлы задачи (в каталоге есть посторонние untracked-файлы с суффиксами « 2»/« 3», их не трогать). Локальный `npx tsc -b` падает на этих дубликатах — проверять типы временным tsconfig с `exclude` `**/* 2.*`, `**/* 3.*`.
- Python-тесты: `.venv/bin/python -m pytest -q`; фронт: `cd frontend && npm test`.

---

## Структура файлов

| Файл | Ответственность |
|---|---|
| `cost/v2/schemas/organization.py`, `equipment.py`, `materials.py` (изменить) | поля §4.2, значение `OTHER` у вида техники |
| `frontend/src/pages/references/enumLabels.ts` (изменить) | подпись `OTHER` уже есть («Прочее»); проверка |
| `migrations/versions/20260904_0006_public_links.py` (создать) | таблицы `public_links`, `public_mirror_sections` |
| `cost/v2/repository.py`, `cost/v2/db_repository.py` (изменить) | `PublicLink`, методы связей и переключателей зеркал (in-memory и PostgreSQL) |
| `cost/v2/public_sync/__init__.py`, `mapping.py`, `reader.py`, `delta.py` (создать) | сопоставление, чтение `public`, расчёт разницы |
| `api/schemas/economics.py` (изменить) | `PublicDeltaRequest/Response`, `PublicLinkRequest` |
| `api/services/public_sync_service.py` (создать) | зависимость `get_public_reader`, сборка ответа |
| `api/routers/economics.py` (изменить) | `POST /references/public-delta`, `POST /references/public-links` |
| `frontend/src/types/economics.ts`, `api/endpoints.ts` (изменить) | типы и вызовы |
| `frontend/src/pages/references/PublicDeltaBanner.tsx`, `publicDelta.ts`, `publicDelta.test.ts` (создать) | плашка и чистая функция применения предложений |
| `frontend/src/pages/references/ReferencesPage.tsx` (изменить) | загрузка разницы, применение, связывание |
| `tests/pg_public.py` (создать) | фикстура тестовой базы с DDL `public` |
| `tests/test_public_sync_mapping.py`, `test_public_sync_delta.py`, `test_public_sync_reader_pg.py`, `test_api_public_delta.py`, `test_reference_schemas.py`, `test_repository_organization_isolation.py` | тесты |
| `Docs/specs/2026-09-03-unified-references-design.md` (изменить) | §12: пункт 3 делится на 3a и 3b |

---

### Task 0: Ветка и уточнение спецификации

- [ ] **Step 1: Ветка**

```bash
git checkout main && git pull -q origin main && git checkout -b feat/public-exchange-pull
```

- [ ] **Step 2: §12 спецификации**

В `Docs/specs/2026-09-03-unified-references-design.md` пункт 3 списка в §12 заменить на два:

```
3. Получение из `public`: новые поля схем, таблица связей, чтение таблиц
   журнала, разница с черновиком и её применение (§4.1–§4.4, §10 — тестовая
   база).
4. Выгрузка в `public` при публикации, зеркала разделов, скрипт прав (§4.5,
   §5, §10 — скрипт).
```

и фразу «Три отдельных PR» на «Четыре отдельных PR».

- [ ] **Step 3: Коммит**

```bash
git add Docs/specs/2026-09-03-unified-references-design.md
git commit -m "docs(specs): обмен с public делится на получение и выгрузку

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 1: Поля схем для обмена (§4.2)

**Files:**
- Modify: `cost/v2/schemas/organization.py` (`CounterpartyPayload`, `SitePayload`), `cost/v2/schemas/equipment.py` (`EquipmentTypePayload`, `EquipmentAssetPayload`), `cost/v2/schemas/materials.py` (`MaterialPayload`)
- Test: `tests/test_reference_schemas.py`

**Interfaces:**
- `SitePayload.short_name: str | None` (`max_length=5`), `mineral_type: str | None`, `customer_legal_name: str | None`;
- `CounterpartyPayload.short_name: str | None`;
- `EquipmentTypePayload.kind` — `Literal["DRILL_RIG", "SZM", "HAZMAT_TRUCK", "LIGHT_VEHICLE", "TRACTOR", "OTHER"]`, `brand: str | None`, `machine_type_name: str | None`;
- `EquipmentAssetPayload.serial_number: str | None`;
- `MaterialPayload.lifetime_m`, `diameter_mm`, `delay_ms: Decimal | None` (единицы `м`, `мм`, `мс`), `thread_type: str | None`.

- [ ] **Step 1: Тест**

В `tests/test_reference_schemas.py` добавить класс:

```python
class TestPublicExchangeFields:
    """Поля, без которых обмен со схемой public теряет данные (спецификация §4.2)."""

    def test_site_fields(self):
        from cost.v2.schemas.organization import SitePayload

        payload = SitePayload(short_name="ЛОМ", mineral_type="нерудные материалы", customer_legal_name='АО "ТК"')
        assert payload.short_name == "ЛОМ"
        with pytest.raises(ValidationError):
            SitePayload(short_name="СЛИШКОМ")
        schema = section_json_schema("sites")
        assert schema["properties"]["short_name"]["title"] == "Краткое имя"
        assert schema["properties"]["customer_legal_name"]["title"] == "Заказчик текстом"

    def test_counterparty_short_name(self):
        from cost.v2.schemas.organization import CounterpartyPayload

        assert CounterpartyPayload(short_name='ООО "ПОМБУР"').short_name == 'ООО "ПОМБУР"'

    def test_equipment_fields_and_other_kind(self):
        from cost.v2.schemas.equipment import EquipmentAssetPayload, EquipmentTypePayload

        item = EquipmentTypePayload(kind="OTHER", brand="INTEO", machine_type_name="Самосвал")
        assert item.kind == "OTHER" and item.brand == "INTEO"
        asset = EquipmentAssetPayload(equipment_type_code="T", serial_number="JK2526063L")
        assert asset.serial_number == "JK2526063L"
        assert "OTHER" in section_json_schema("equipment_types")["properties"]["kind"]["enum"]

    def test_material_tool_and_delay_fields(self):
        from cost.v2.schemas.materials import MaterialPayload

        tool = MaterialPayload(lifetime_m=Decimal("600"), diameter_mm=Decimal("152"), thread_type="DHD350")
        assert tool.lifetime_m == Decimal("600")
        schema = section_json_schema("materials")["properties"]
        assert schema["lifetime_m"]["x-unit"] == "м"
        assert schema["diameter_mm"]["x-unit"] == "мм"
        assert schema["delay_ms"]["x-unit"] == "мс"
        assert MaterialPayload(delay_ms=Decimal("42")).delay_ms == Decimal("42")
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `.venv/bin/python -m pytest tests/test_reference_schemas.py -k PublicExchange -q`
Expected: FAIL, `Extra inputs are not permitted`.

- [ ] **Step 3: Поля**

`cost/v2/schemas/organization.py`:
- в `CounterpartyPayload` после `inn` добавить
  `short_name: str | None = Field(default=None, title="Краткое наименование", description="Как в журнале буровых работ, например АО \"Теплогорский карьер\"")`;
- в `SitePayload` после `customer_code` добавить:

```python
    customer_legal_name: str | None = Field(
        default=None,
        title="Заказчик текстом",
        description="Наименование заказчика из журнала, если контрагента нет в справочнике",
    )
    short_name: str | None = Field(
        default=None, max_length=5, title="Краткое имя", description="Код объекта в журнале буровых работ (до 5 символов)"
    )
    mineral_type: str | None = Field(
        default=None, title="Полезное ископаемое", description="Вид сырья по журналу, например «нерудные материалы»"
    )
```

`cost/v2/schemas/equipment.py`:
- `kind: Literal["DRILL_RIG", "SZM", "HAZMAT_TRUCK", "LIGHT_VEHICLE", "TRACTOR", "OTHER"]`, в `description` добавить «OTHER — прочая техника без норм модели»;
- после `kind` добавить `brand: str | None = Field(default=None, title="Марка", description="Производитель или марка по журналу")` и `machine_type_name: str | None = Field(default=None, title="Тип машины по журналу", description="Название типа машины в журнале буровых работ")`;
- в `EquipmentAssetPayload` после `inventory_number` добавить `serial_number: str | None = Field(default=None, title="Заводской номер", description="Серийный номер по журналу")`.

`cost/v2/schemas/materials.py`, в `MaterialPayload` после `length_m`:

```python
    lifetime_m: Decimal | None = UnitField("м", title="Ресурс", description="Ресурс бурового инструмента", default=None)
    diameter_mm: Decimal | None = UnitField("мм", title="Диаметр", description="Диаметр инструмента", default=None)
    thread_type: str | None = Field(default=None, title="Хвостовик / резьба", description="Тип хвостовика или резьбы")
    delay_ms: Decimal | None = UnitField("мс", title="Замедление", description="Стандартный интервал замедления СИ", default=None)
```

Проверить, что модель себестоимости не перечисляет виды техники жёстко: `grep -rn "LIGHT_VEHICLE\|TRACTOR" cost/model cost/v2/engine.py` — ожидается пусто (иначе добавить `OTHER` рядом с `LIGHT_VEHICLE`).

- [ ] **Step 4: Тесты**

Run: `.venv/bin/python -m pytest tests/test_reference_schemas.py tests/test_api_reference_schema.py tests/test_legacy_adapter.py -q`
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add cost/v2/schemas/organization.py cost/v2/schemas/equipment.py cost/v2/schemas/materials.py tests/test_reference_schemas.py
git commit -m "feat(schemas): поля для обмена со схемой public

Краткое имя, полезное ископаемое и заказчик текстом у объекта, краткое
наименование контрагента, марка и тип машины по журналу, заводской номер,
ресурс, диаметр, хвостовик и замедление у материалов; вид техники OTHER.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Таблицы связей и переключателей зеркал

**Files:**
- Create: `migrations/versions/20260904_0006_public_links.py`
- Modify: `cost/v2/repository.py`, `cost/v2/db_repository.py`
- Test: `tests/test_repository_organization_isolation.py`

**Interfaces:**
- `cost/v2/repository.py`:

```python
@dataclass(frozen=True)
class PublicLink:
    section: str
    code: str
    public_table: str
    public_id: int
    synced_at: datetime | None = None
```

- методы репозитория (протокол, in-memory, PostgreSQL):
  - `list_public_links(self, organization_id: str) -> Sequence[PublicLink]`
  - `save_public_link(self, organization_id: str, user_id: str, link: PublicLink) -> PublicLink` — upsert по (`organization_id`, `section`, `code`); если (`public_table`, `public_id`) уже связаны с другой записью, поднять `EconomicsRepositoryError("Запись public {table}#{id} уже связана с {section}/{code}")`;
  - `list_mirror_sections(self, organization_id: str) -> dict[str, bool]`
  - `set_mirror_section(self, organization_id: str, user_id: str, section: str, enabled: bool) -> None`

- [ ] **Step 1: Тесты**

В `tests/test_repository_organization_isolation.py` добавить:

```python
def test_public_links_are_organization_scoped_and_unique(repository) -> None:
    from cost.v2.repository import EconomicsRepositoryError, PublicLink

    link = PublicLink(section="sites", code="SITE_LOM", public_table="sites", public_id=1)
    saved = repository.save_public_link(ORG_A, "a@example.ru", link)
    assert saved.synced_at is not None
    assert [l.code for l in repository.list_public_links(ORG_A)] == ["SITE_LOM"]
    assert repository.list_public_links(ORG_B) == ()

    repository.save_public_link(ORG_A, "a@example.ru", PublicLink("sites", "SITE_LOM", "sites", 2))
    assert [l.public_id for l in repository.list_public_links(ORG_A)] == [2]
    with pytest.raises(EconomicsRepositoryError):
        repository.save_public_link(ORG_A, "a@example.ru", PublicLink("sites", "SITE_OTHER", "sites", 2))


def test_mirror_sections_are_organization_scoped(repository) -> None:
    repository.set_mirror_section(ORG_A, "a@example.ru", "rocks", True)
    assert repository.list_mirror_sections(ORG_A) == {"rocks": True}
    assert repository.list_mirror_sections(ORG_B) == {}
    repository.set_mirror_section(ORG_A, "a@example.ru", "rocks", False)
    assert repository.list_mirror_sections(ORG_A) == {"rocks": False}
```

- [ ] **Step 2: Убедиться, что тесты падают** — `.venv/bin/python -m pytest tests/test_repository_organization_isolation.py -q` → `AttributeError`.

- [ ] **Step 3: Миграция**

Создать `migrations/versions/20260904_0006_public_links.py`:

```python
"""Связи записей blastex с таблицами схемы public и переключатели зеркал.

`public_links` хранит, какой записи журнала буровых работ соответствует
запись справочника; `public_mirror_sections` — какие разделы выгружаются
зеркалом `public.blastex_<section>` (спецификация §4.3, §5).

Revision ID: 20260904_0006
Revises: 20260903_0005
Create Date: 2026-09-04
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260904_0006"
down_revision = "20260903_0005"
branch_labels = None
depends_on = None

SCHEMA = "blastex"


def upgrade() -> None:
    op.create_table(
        "public_links",
        sa.Column("organization_id", sa.String(length=120), nullable=False),
        sa.Column("section", sa.String(length=64), nullable=False),
        sa.Column("code", sa.String(length=120), nullable=False),
        sa.Column("public_table", sa.String(length=64), nullable=False),
        sa.Column("public_id", sa.Integer(), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=320), nullable=False),
        sa.PrimaryKeyConstraint("organization_id", "section", "code", name="pk_public_links"),
        sa.UniqueConstraint("public_table", "public_id", name="uq_public_links_public_row"),
        schema=SCHEMA,
    )
    op.create_table(
        "public_mirror_sections",
        sa.Column("organization_id", sa.String(length=120), nullable=False),
        sa.Column("section", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=320), nullable=False),
        sa.PrimaryKeyConstraint("organization_id", "section", name="pk_public_mirror_sections"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("public_mirror_sections", schema=SCHEMA)
    op.drop_table("public_links", schema=SCHEMA)
```

- [ ] **Step 4: Репозиторий**

`cost/v2/repository.py`: после `LegacyWorkspaceSettings` добавить `PublicLink` (выше); в протокол — четыре метода; в `InMemoryEconomicsRepository.__init__` — `self._public_links: dict[tuple[str, str, str], PublicLink] = {}` и `self._mirror_sections: dict[tuple[str, str], bool] = {}`; реализация:

```python
    def list_public_links(self, organization_id: str) -> Sequence[PublicLink]:
        with self._lock:
            return tuple(
                link for (org, _s, _c), link in sorted(self._public_links.items()) if org == organization_id
            )

    def save_public_link(self, organization_id: str, user_id: str, link: PublicLink) -> PublicLink:
        with self._lock:
            for (org, section, code), existing in self._public_links.items():
                same_row = existing.public_table == link.public_table and existing.public_id == link.public_id
                if same_row and (org, section, code) != (organization_id, link.section, link.code):
                    raise EconomicsRepositoryError(
                        f"Запись public {link.public_table}#{link.public_id} уже связана с {section}/{code}."
                    )
            saved = PublicLink(
                section=link.section,
                code=link.code,
                public_table=link.public_table,
                public_id=link.public_id,
                synced_at=datetime.now(timezone.utc).replace(microsecond=0),
            )
            self._public_links[(organization_id, link.section, link.code)] = saved
            return saved

    def list_mirror_sections(self, organization_id: str) -> dict[str, bool]:
        with self._lock:
            return {section: enabled for (org, section), enabled in self._mirror_sections.items() if org == organization_id}

    def set_mirror_section(self, organization_id: str, user_id: str, section: str, enabled: bool) -> None:
        with self._lock:
            self._mirror_sections[(organization_id, section)] = enabled
```

`cost/v2/db_repository.py`: ORM-строки

```python
class PublicLinkRow(Base):
    __tablename__ = "public_links"
    __table_args__ = (
        UniqueConstraint("public_table", "public_id", name="uq_public_links_public_row"),
        {"schema": SCHEMA},
    )

    organization_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    section: Mapped[str] = mapped_column(String(64), primary_key=True)
    code: Mapped[str] = mapped_column(String(120), primary_key=True)
    public_table: Mapped[str] = mapped_column(String(64), nullable=False)
    public_id: Mapped[int] = mapped_column(Integer, nullable=False)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(320), nullable=False)


class PublicMirrorSectionRow(Base):
    __tablename__ = "public_mirror_sections"
    __table_args__ = ({"schema": SCHEMA},)

    organization_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    section: Mapped[str] = mapped_column(String(64), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(320), nullable=False)
```

(проверить импорты `Integer`, `Boolean`, `UniqueConstraint` из `sqlalchemy`) и методы по тому же контракту: `save_public_link` в одной транзакции ищет строку с тем же (`public_table`, `public_id`) и другим ключом → `EconomicsRepositoryError`; иначе `session.merge`-подобный upsert по первичному ключу.

- [ ] **Step 5: Тесты** — `.venv/bin/python -m pytest tests/test_repository_organization_isolation.py tests/test_cost_v2_repository.py -q` → PASS (включая проверку «organization_id первым»).

- [ ] **Step 6: Локальная миграция**, если Docker запущен: `BLASTEX_DATABASE_URL=<из launch.json> .venv/bin/alembic upgrade head` и `docker exec blastex-pg-dev psql -U blastex -d project1 -c '\d blastex.public_links'`. Если Docker выключен — отметить в отчёте, проверка переносится в Task 8.

- [ ] **Step 7: Коммит**

```bash
git add migrations/versions/20260904_0006_public_links.py cost/v2/repository.py cost/v2/db_repository.py tests/test_repository_organization_isolation.py
git commit -m "feat(repository): связи записей с public и переключатели зеркал

Таблицы blastex.public_links и public_mirror_sections, методы репозитория
в памяти и PostgreSQL с изоляцией по организации.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Тестовая база с DDL public

**Files:**
- Create: `tests/pg_public.py`
- Test: `tests/test_public_sync_reader_pg.py` (создаётся здесь, наполняется в Task 4)

**Interfaces:**
- `tests/pg_public.py`:
  - `TEST_DATABASE_URL = os.getenv("BLASTEX_TEST_DATABASE_URL", "").strip()`;
  - `requires_pg = pytest.mark.skipif(not TEST_DATABASE_URL, reason="BLASTEX_TEST_DATABASE_URL не задан")`;
  - фикстура `public_db` (function scope): создаёт движок, выполняет `DROP SCHEMA public CASCADE; CREATE SCHEMA public;`, загружает `Docs/public_schema.sql` без строки `CREATE SCHEMA public AUTHORIZATION user1;` и без строк `-- ...`, выполняя statements по одному (разделитель `;\n`), затем `alembic upgrade head` для схемы `blastex` (через `subprocess` с `BLASTEX_DATABASE_URL=TEST_DATABASE_URL`), отдаёт `sqlalchemy.Engine`; после теста ничего не чистит (следующий тест пересоздаёт схему);
  - `seed_public(engine)` вставляет минимальный набор из §13: 2 контрагента (`АО "Теплогорский карьер"` клиент, `ООО "ПОМБУР"` поставщик), 2 объекта (ЛОМ с `client_legal_name = 'АО "Теплогорский карьер"'`, ЦСТ без совпадения), тип машины «Буровая установка», модель `JK830-2` (brand `JK Drilling`), единицу `Б-01`, 2 типа СИ, 1 тип инструмента с `expected_lifetime_meters=600`, `diameter=152`, спецификацию закупки с 1 позицией, 1 инструмент в `tools_inventory` с `purchase_price` и `supplier_id`; возвращает dict с id.

Файл содержит только фикстуры и помощники; никакой логики продукта.

- [ ] **Step 1: Написать `tests/pg_public.py`** по интерфейсу выше. DDL читать так:

```python
def _statements(ddl: str) -> list[str]:
    body = "\n".join(line for line in ddl.splitlines() if not line.strip().startswith("--"))
    body = body.replace("CREATE SCHEMA public AUTHORIZATION user1;", "")
    return [part.strip() for part in body.split(";\n") if part.strip()]
```

Функцию `rls_auto_enable` из DDL пропустить (statement, содержащий `CREATE OR REPLACE FUNCTION public.rls_auto_enable`): событийные триггеры требуют суперпользователя, а RLS на тестовые таблицы включает сам DDL (`ENABLE ROW LEVEL SECURITY`); владелец таблиц — тестовая роль, для неё RLS не действует.

- [ ] **Step 2: Дымовой тест** в `tests/test_public_sync_reader_pg.py`:

```python
from tests.pg_public import requires_pg, seed_public

pytestmark = requires_pg


def test_public_schema_loads_and_seeds(public_db) -> None:
    ids = seed_public(public_db)
    from sqlalchemy import text

    with public_db.connect() as conn:
        assert conn.execute(text("select count(*) from public.sites")).scalar() == 2
        assert conn.execute(text("select count(*) from blastex.public_links")).scalar() == 0
    assert ids["site_lom"] > 0
```

Убедиться, что без переменной тест помечен `SKIPPED`: `.venv/bin/python -m pytest tests/test_public_sync_reader_pg.py -q -rs`. Если Docker запущен, прогнать с `BLASTEX_TEST_DATABASE_URL=postgresql+psycopg://blastex:<пароль из launch.json>@127.0.0.1:5433/project1_test` — базу `project1_test` создать один раз: `docker exec blastex-pg-dev psql -U blastex -d postgres -c 'create database project1_test'`. Никогда не указывать `project1`: фикстура удаляет схему `public`.

- [ ] **Step 3: Коммит**

```bash
git add tests/pg_public.py tests/test_public_sync_reader_pg.py
git commit -m "test: тестовая база PostgreSQL со схемой public из Docs/public_schema.sql

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Сопоставление и чтение таблиц public

**Files:**
- Create: `cost/v2/public_sync/__init__.py`, `cost/v2/public_sync/mapping.py`, `cost/v2/public_sync/reader.py`
- Test: `tests/test_public_sync_mapping.py`, `tests/test_public_sync_reader_pg.py`

**Interfaces (`mapping.py`):**

```python
@dataclass(frozen=True)
class PublicRow:            # строка таблицы public, уже прочитанная
    table: str
    id: int
    values: Mapping[str, Any]

@dataclass(frozen=True)
class PublicSnapshot:       # всё, что нужно для расчёта разницы
    rows: Mapping[str, tuple[PublicRow, ...]]   # table -> rows
    def table(self, name: str) -> tuple[PublicRow, ...]

TABLES: tuple[str, ...] = (
    "counterparties", "sites", "machine_types", "equipment_models", "equipment_units",
    "initiating_device_types", "delay_series", "tool_types", "tools_inventory",
    "explosive_material_prices", "explosive_spec_items", "explosive_purchase_specs", "contracts",
)

MACHINE_KINDS: dict[str, str] = {
    "Буровая установка": "DRILL_RIG",
    "Машина смесительно-зарядная": "SZM",
    "Автомобиль для перевозки взрывчатых веществ": "HAZMAT_TRUCK",
    "Вахтовый автобус": "LIGHT_VEHICLE",
    "Бульдозер": "TRACTOR", "Экскаватор": "TRACTOR", "Погрузчик": "TRACTOR",
}

def normalize_legal_name(text: str) -> str        # регистр, пробелы, кавычки «»“”"' → "
def public_code(table: str, public_id: int) -> str  # PUB_SITE_12, PUB_COUNTERPARTY_5, PUB_MODEL_2, PUB_UNIT_1, PUB_IDT_3, PUB_TOOL_4
def kind_for_machine_type(name: str | None) -> str  # словарь, иначе "OTHER"

@dataclass(frozen=True)
class Proposal:             # одна запись blastex, построенная из public
    section: str
    public_table: str
    public_id: int
    code: str
    name: str
    payload: dict[str, Any]
    is_active: bool
    shared_fields: tuple[str, ...]   # какие поля считаются «общими» (для сравнения)

def build_proposals(snapshot: PublicSnapshot, counterparty_codes: Mapping[int, str], type_codes: Mapping[int, str]) -> list[Proposal]
```

`build_proposals` строит записи по §4.1 в порядке: контрагенты → объекты → типы техники → основные средства → материалы СИ → материалы инструмент → цены. Ссылки внутри `public` (объект → заказчик текстом, единица → модель, цена → тип СИ/инструмента/поставщик) переводятся в коды blastex через `counterparty_codes`/`type_codes` (id → код уже связанной или предлагаемой записи); `build_proposals` сам дополняет эти словари кодами `PUB_*` для строк без связи.

Общие поля по §4.1:
- `sites`: `name`, `short_name`, `mineral_type`, `is_active`, `customer_code` (если нашёлся по нормализованному имени среди контрагентов snapshot'а) иначе `customer_legal_name`;
- `counterparties`: `name`, `short_name`, `inn`, `role` (`CUSTOMER` если `is_client`, иначе `SUPPLIER`), `is_active`;
- `equipment_types` из `equipment_models`: `name` = `model_name`, `brand`, `machine_type_name` = `machine_types.name`, `kind` по словарю (только для новой записи — см. Task 5);
- `equipment_assets` из `equipment_units`: `name` = `internal_id`, `inventory_number` = `internal_id`, `serial_number`, `equipment_type_code` по модели, `is_active` = `status != 'Списано'`;
- `materials` СИ: `name`, `comment` = `description`, `material_kind = "СИ"`, `storage_class = "NSI"`, `delay_ms` = `delay_series.delay_ms` с `is_standard`;
- `materials` инструмент: `name`, `comment` = `description`, `material_kind = "Буровой инструмент"`, `lifetime_m`, `diameter_mm`, `thread_type`;
- `material_prices` (только новые/изменённые, никогда не выгружаются): из `explosive_material_prices` (`price_rub = price_per_unit_base / unit_conversion_factor`, `supplier_code` по `contracts.counterparty_id`, `valid_from`, `valid_to`), из `explosive_spec_items` + `explosive_purchase_specs` (`price_rub = price_per_unit_no_vat / conversion_factor`, `delivery_rub = price_rub * total_delivery_cost_no_vat / sum(quantity_ordered * price_per_unit_no_vat)` по спецификации, `valid_from = spec_date`, `supplier_code` по договору спецификации, если есть), из `tools_inventory` (последняя по `purchase_date` покупка на пару тип инструмента + поставщик: `price_rub = purchase_price`, `valid_from = purchase_date`). Числа — строками `Decimal` без экспоненты (`format(value, "f")`).

**Interfaces (`reader.py`):**

```python
class PublicUnavailable(RuntimeError): ...   # текст — русский, с причиной

class PublicReader(Protocol):
    def read(self) -> PublicSnapshot: ...

class SqlPublicReader:
    def __init__(self, engine: Engine) -> None
    def read(self) -> PublicSnapshot   # SELECT * из каждой таблицы TABLES; отсутствие таблицы/схемы/прав → PublicUnavailable

class StaticPublicReader:              # для тестов и API без базы
    def __init__(self, snapshot: PublicSnapshot) -> None
```

- [ ] **Step 1: Тесты сопоставления** (`tests/test_public_sync_mapping.py`, без базы): построить `PublicSnapshot` из dict-строк по §13 (контрагент `Акционерное общество "Теплогорский карьер"` с `short_name 'АО "Теплогорский карьер"'`, объект ЛОМ с `client_legal_name 'АО «Теплогорский карьер»'` — другие кавычки, объект ЦСТ с `'ООО "Директ-Склад"'` без контрагента, тип машины «Самосвал», модель, единица со статусом «Списано», два типа СИ, `delay_series`, тип инструмента, спецификация с двумя позициями и доставкой 131147.54, `tools_inventory` с двумя покупками одного типа) и проверить:
  - коды `PUB_COUNTERPARTY_1`, `PUB_SITE_1`, `PUB_MODEL_1`, `PUB_UNIT_1`, `PUB_IDT_1`, `PUB_TOOL_1`;
  - у ЛОМ `customer_code == "PUB_COUNTERPARTY_1"` и нет `customer_legal_name`; у ЦСТ `customer_legal_name == 'ООО "Директ-Склад"'` и нет `customer_code`;
  - `kind_for_machine_type("Самосвал") == "OTHER"`, `("Буровая установка") == "DRILL_RIG"`;
  - единица «Списано» → `is_active is False`, `equipment_type_code == "PUB_MODEL_1"`;
  - СИ получает `delay_ms` только от `is_standard` серии;
  - цена спецификации: `price_rub` и `delivery_rub` посчитаны по формуле (взять числа: позиция 2.52 × 335162.90 и 2.00 × 239543.85, доставка 131147.54 → `delivery_rub` первой позиции = `335162.90/1000 * 131147.54 / (2.52*335162.90 + 2.00*239543.85)` с точностью до копейки);
  - `tools_inventory`: берётся покупка с поздней датой;
  - `normalize_legal_name('АО «Теплогорский  карьер»') == normalize_legal_name('ао "теплогорский карьер"')`.

- [ ] **Step 2: Убедиться, что падают** (модуль отсутствует).

- [ ] **Step 3: Реализовать `mapping.py` и `reader.py`** по интерфейсам. В `SqlPublicReader.read` каждую таблицу читать `text(f'SELECT * FROM public."{table}"')` внутри `engine.connect()`; ловить `sqlalchemy.exc.ProgrammingError`/`OperationalError` и поднимать `PublicUnavailable(f"Схема public недоступна: {причина}")`, где причина — первая строка `str(exc.orig)`.

- [ ] **Step 4: Тест чтения с базой** в `tests/test_public_sync_reader_pg.py`:

```python
def test_sql_reader_reads_seeded_tables(public_db) -> None:
    from cost.v2.public_sync.reader import SqlPublicReader

    seed_public(public_db)
    snapshot = SqlPublicReader(public_db).read()
    assert len(snapshot.table("sites")) == 2
    assert snapshot.table("sites")[0].values["full_name"]


def test_sql_reader_reports_missing_schema(public_db) -> None:
    from sqlalchemy import text
    from cost.v2.public_sync.reader import PublicUnavailable, SqlPublicReader

    with public_db.begin() as conn:
        conn.execute(text("DROP TABLE public.sites CASCADE"))
    with pytest.raises(PublicUnavailable, match="public"):
        SqlPublicReader(public_db).read()
```

- [ ] **Step 5: Прогон** — `.venv/bin/python -m pytest tests/test_public_sync_mapping.py tests/test_public_sync_reader_pg.py -q -rs` → PASS (pg-тесты SKIPPED без переменной).

- [ ] **Step 6: Коммит**

```bash
git add cost/v2/public_sync tests/test_public_sync_mapping.py tests/test_public_sync_reader_pg.py
git commit -m "feat(public-sync): сопоставление разделов blastex с таблицами public и чтение журнала

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Разница между public и черновиком

**Files:**
- Create: `cost/v2/public_sync/delta.py`
- Test: `tests/test_public_sync_delta.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class FieldChange:
    key: str            # "name", "payload.short_name", "is_active"
    old: Any
    new: Any

@dataclass(frozen=True)
class DeltaEntry:
    kind: Literal["new", "changed", "deactivated"]
    section: str
    public_table: str
    public_id: int
    code: str                      # код в черновике (для changed/deactivated) или PUB_* (new)
    name: str
    item: dict[str, Any]           # готовая запись blastex (ReferenceItem.to_dict()) — для new; для changed — запись черновика с применёнными общими полями
    changes: tuple[FieldChange, ...]

@dataclass(frozen=True)
class PublicDelta:
    entries: tuple[DeltaEntry, ...]
    counts: dict[str, int]          # {"new": n, "changed": m, "deactivated": k}

def compute_delta(
    snapshot: PublicSnapshot,
    links: Sequence[PublicLink],
    draft: Mapping[str, Sequence[ReferenceItem]],
) -> PublicDelta
```

Правила:
- строка `public` без связи → `new` с кодом `PUB_*`; если в черновике уже есть запись с таким кодом (пользователь применил раньше, но связь ещё не сохранена) — считать её связанной;
- строка со связью: сравнить общие поля с записью черновика (для `equipment_types` поле `kind` не сравнивается и не меняется — словарь только при создании); есть различия → `changed` с `changes` и `item` = запись черновика + новые значения; `is_active=false` в `public` при активной записи → `deactivated` (без других изменений);
- связь есть, а записи в черновике нет (удалена) → пропустить;
- цены (`material_prices`): `new`, если кода `PRICE_PUB_*` нет в черновике, `changed`, если есть и отличаются `price_rub`/`delivery_rub`/`valid_from`/`valid_to`/`supplier_code`; связи для цен не нужны (код детерминирован);
- ссылки в предложениях (`customer_code`, `equipment_type_code`, `material_code`, `supplier_code`) указывают на коды из связей, если они есть, иначе на `PUB_*` соседних предложений — `build_proposals` получает словари кодов, собранные из `links`.

- [ ] **Step 1: Тесты** (`tests/test_public_sync_delta.py`, без базы): snapshot из Task 4 плюс `links` и `draft`:
  - без связей и с пустым черновиком → все записи `new`, `counts["new"]` равно числу строк + цен, порядок: контрагенты, объекты, типы, единицы, СИ, инструмент, цены;
  - связь `sites/SITE_LOM ↔ sites#1`, в черновике `SITE_LOM` с `short_name "ЛОМ"`, в public `short_name "ЛМ"` → одна запись `changed` с `FieldChange("payload.short_name", "ЛОМ", "ЛМ")`; `item["payload"]["mobilization_km"]` из черновика сохраняется;
  - связь есть, `is_active=false` в public, запись активна → `deactivated`;
  - связь есть, всё совпадает → записи нет;
  - связь `equipment_types/TYPE_JK ↔ equipment_models#1`, в черновике `kind "DRILL_RIG"`, у модели тип машины «Самосвал» → `kind` не в `changes`;
  - цена спецификации в черновике с другой `price_rub` → `changed`.

- [ ] **Step 2: Убедиться, что падают.** **Step 3: Реализовать `delta.py`.** **Step 4: Прогон** `tests/test_public_sync_*.py` → PASS.

- [ ] **Step 5: Коммит**

```bash
git add cost/v2/public_sync/delta.py tests/test_public_sync_delta.py
git commit -m "feat(public-sync): разница между журналом public и черновиком справочников

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: API получения разницы и связывания

**Files:**
- Create: `api/services/public_sync_service.py`
- Modify: `api/schemas/economics.py`, `api/routers/economics.py`
- Test: `tests/test_api_public_delta.py`

**Interfaces:**
- `api/services/public_sync_service.py`:
  - `get_public_reader(repository: EconomicsRepository = Depends(get_economics_repository)) -> PublicReader` — для `PostgresEconomicsRepository` возвращает `SqlPublicReader(repository.engine)`; для другого репозитория (тесты) — `StaticPublicReader(PublicSnapshot(rows={}))`; тесты переопределяют зависимость;
  - `public_delta_payload(reader, repository, organization_id, sections: dict[str, list[ReferenceItemSchema]]) -> dict` — `{"available": True, "error": "", "counts": {...}, "entries": [...]}`; при `PublicUnavailable` — `{"available": False, "error": str(exc), "counts": {"new":0,"changed":0,"deactivated":0}, "entries": []}`.
- Схемы: `PublicDeltaRequest(sections)` (как `ReferenceValidateRequest`), `PublicFieldChangeSchema(key, old, new)`, `PublicDeltaEntrySchema(kind, section, public_table, public_id, code, name, item: ReferenceItemSchema, changes)`, `PublicDeltaResponse(available, error, counts, entries)`, `PublicLinkRequest(section, code, public_table, public_id)`, `PublicLinkSchema(section, code, public_table, public_id, synced_at)`.
- Маршруты:
  - `POST /economics/references/public-delta` — `require_internal_access`;
  - `POST /economics/references/public-links` — `require_reference_editor`; `EconomicsRepositoryError` → 409 с текстом;
  - `GET /economics/references/public-links` — список связей организации.

- [ ] **Step 1: Тесты** (`tests/test_api_public_delta.py`, образец `_client` из `tests/test_api_reference_files.py`, плюс `app.dependency_overrides[get_public_reader] = lambda: StaticPublicReader(snapshot)` со snapshot из Task 4):
  - разница для пустого черновика: `available` true, `counts["new"] > 0`, первая запись — контрагент;
  - после `POST /public-links` для `sites/SITE_LOM ↔ sites#1` и черновика с `SITE_LOM` разница показывает `changed`, а не `new`;
  - повторная связь той же строки public с другим кодом → 409;
  - роль `user` → 403 на `public-links`, 200 на `public-delta`;
  - reader, бросающий `PublicUnavailable("Схема public недоступна: нет прав")` → 200, `available` false, текст в `error`.

- [ ] **Step 2: Убедиться, что падают (404).** **Step 3: Реализовать.** **Step 4: Прогон** `tests/test_api_public_delta.py tests/test_api_economics.py -q` → PASS.

- [ ] **Step 5: Коммит**

```bash
git add api/services/public_sync_service.py api/schemas/economics.py api/routers/economics.py tests/test_api_public_delta.py
git commit -m "feat(api): разница с журналом public и связи записей

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: Плашка «Из project1» на странице «Справочники»

**Files:**
- Modify: `frontend/src/types/economics.ts`, `frontend/src/api/endpoints.ts`
- Create: `frontend/src/pages/references/publicDelta.ts`, `publicDelta.test.ts`, `PublicDeltaBanner.tsx`
- Modify: `frontend/src/pages/references/ReferencesPage.tsx`

**Interfaces:**
- типы `PublicDelta`, `PublicDeltaEntry`, `PublicFieldChange`, `PublicLink` (зеркало схем Task 6);
- `api.economics.publicDelta(sections)`, `api.economics.publicLinks()`, `api.economics.savePublicLink(link)`;
- `publicDelta.ts`: `applyDeltaEntries(draft, entries, makeRowId) -> { draft, applied: number }` — `new` добавляет запись в раздел (если кода нет), `changed`/`deactivated` заменяет запись с тем же кодом на `entry.item` (сохраняя `row_id`); чистая функция без знаний о полях;
- `PublicDeltaBanner` props: `delta: PublicDelta | null`, `busy`, `canEdit`, `onRefresh()`, `onApplyAll()`, `onLink(entry, code)` с селектом активных записей раздела для `new` (список приходит из страницы: `recordsOf(section) -> {code, name}[]`); текст «Из project1: N новых, M изменённых, K деактивированных»; при `available === false` — «project1 недоступен: <error>» и кнопка «Повторить»; при `counts` все нули — плашка не показывается.

- [ ] **Step 1: vitest для `applyDeltaEntries`** (новая запись добавляется; повтор кода не дублирует; `changed` заменяет запись и сохраняет `row_id`; разделы без записей не создаются пустыми... либо создаются — зафиксировать: создаются).
- [ ] **Step 2: Реализация**: типы, эндпоинты, компонент, интеграция в `ReferencesPage` — запрос разницы после `load()` и после публикации, кнопка «Проверить project1» в плашке, «Применить в черновик» → `applyDeltaEntries` + `setNewRows` для новых кодов + повторный расчёт разницы; «Связать с существующей записью» → `savePublicLink` → повторный расчёт. Плашка вставляется между `<header className="ref-workbench-head">` и `{error && ...}`. Классы: `page-caption`, `ref-ghost-button`, `primary-button`; новый класс `ref-public-banner` добавить в `frontend/src/styles.css` рядом с `.ref-publish-bar` (один блок с рамкой и отступом).
- [ ] **Step 3: `npm test` и scoped `tsc`.**
- [ ] **Step 4: Коммит** `feat(frontend): плашка «Из project1» — разница с журналом и применение в черновик`.

---

### Task 8: Проверка на базе и в браузере

- [ ] **Step 1: Docker.** Если `docker info` не отвечает — попросить пользователя запустить Docker Desktop и остановиться на этом шаге (BLOCKED в отчёте). Иначе: `alembic upgrade head` на `project1` (dev), создать `project1_test`, прогнать pg-тесты с `BLASTEX_TEST_DATABASE_URL`.
- [ ] **Step 2: Схема public в dev-базе.** Загрузить `Docs/public_schema.sql` (без `AUTHORIZATION user1` и функции `rls_auto_enable`) в `project1` контейнера `blastex-pg-dev` и вставить набор `seed_public` (через `tests/pg_public.py` как модуль: `PYTHONPATH=. .venv/bin/python -c "..."`).
- [ ] **Step 3: Браузер.** `api-cost-v2` + `frontend`, вход `admin@example.ru`/`admin123`, «Справочники»: плашка показывает счётчики; «Связать с существующей записью» для ЛОМ ↔ существующего `SITE_LOM`/`SITE_MAIN`; «Применить в черновик» добавляет остальные; проверка проходит; публикация создаёт ревизию; после перезагрузки плашка показывает только то, что ещё не применено (0, если всё применено). Скриншоты плашки до и после.
- [ ] **Step 4: Полный прогон**, коммит правок по итогам, PR на `main` с заголовком «Единые справочники, PR 3a: получение записей из схемы public».

---

## Самопроверка плана

- §4.1 сопоставление и цены — Task 4/5; §4.2 поля — Task 1; §4.3 связи и коды — Task 2/5/6; §4.4 разница, плашка, связывание, недоступность public — Task 5/6/7; §10 тестовая база — Task 3; §11 «разница считается для новых, изменённых и деактивированных» — Task 5; §4.5/§5 — вынесены в PR 3b (Task 0 правит §12).
- Типы: `PublicSnapshot`/`PublicRow`/`Proposal` (Task 4) → `compute_delta` (Task 5) → сервис и схемы (Task 6) → фронт (Task 7); `PublicLink` (Task 2) используется в Task 5/6 с теми же полями.
