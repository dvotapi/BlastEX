# TASK-006 — Схемные справочники: разделы модели экономики и новый интерфейс

## Статус

- Приоритет: P0 (блокирует TASK-007).
- Статус требований: согласовано с владельцем; макет экранов утверждён.
- Документы-основания: `Docs/ADR-001-economics-model.md`, `Docs/REFERENCES_MODEL.md`, макеты `Docs/design/references-positions.png` и `Docs/design/references-drilling-conditions.png`.
- Обязательное условие: не менять формат хранения снимков (`ReferenceSnapshot`, `ReferenceItem.payload` как JSON) и механику «черновик → проверка → атомарная публикация ревизии». Меняется только то, что знает о полях payload, и то, как их редактирует пользователь.

## 1. Контекст и цель

Сейчас вкладка «Справочники project1» показывает каждую запись строкой таблицы, где все содержательные поля лежат в одном поле «Параметры JSON». Бэкенд знает о полях payload только неявно — проверками по строковым ключам в `cost/v2/references.py` (`rate_rub`, `fixed_rub`, `monthly_capacity`…). Фронту нечего рисовать, кроме JSON, пользователь не понимает, что и в каких единицах заполнять, а модель экономики (TASK-007) требует ещё пяти новых разделов с десятками полей.

Цель: у каждого раздела справочника есть **схема полей** на бэкенде; фронт рисует формы по схеме одним универсальным компонентом; интерфейс — три панели «разделы / список / форма записи», без JSON.

## 2. Принятые решения

- Схема раздела = pydantic-модель payload с метаданными UI. Одна модель на раздел, в одном модуле `cost/v2/schemas/`. Поля из `Docs/REFERENCES_MODEL.md` переносятся буквально.
- Схема отдаётся фронту как JSON Schema через `GET /api/v1/economics/references/schema`. Фронт не хранит знания о полях.
- Валидация — одна: `validate_reference_sections` прогоняет payload каждой записи через pydantic-модель раздела и дополняет существующими перекрёстными проверками (ссылки на операции, ресурсы, пакеты). Сообщения — на русском, с кодом раздела, кодом записи и именем поля.
- Ссылочные поля (`position_code`, `equipment_type_code`, `rock_code`, `operation_code`, `site_code`…) объявляются в схеме как `x-ref: <section>`; фронт рисует их селектом по записям этого раздела из текущего черновика.
- Единицы измерения и подсказки — метаданные поля (`x-unit`, `description`), не текст в UI.
- Вычисляемые показатели формы («на один взрыв по нормативу 5 500 ₽ · 2,1 смены», «коммерческая скорость 120 м/смену») считаются на фронте по формулам, продублированным из `cost/model/` (TASK-007) в `frontend/src/lib/referenceDerived.ts`. Это подсказки, не источник истины.
- Новые разделы добавляются в `REFERENCE_SECTION_DEFINITIONS`: `organization_rates`, `drilling_conditions`, `unit_fixed_costs`. Раздел `drilling_productivity` объявляется устаревшим и мигрируется в `drilling_conditions`.
- Переименование полей существующих разделов (`labor_rates.fixed_salary_monthly → fixed_monthly_rub`, `piece_rate_per_m3 → piece_rate_rub + piece_unit + piece_driver`) делается миграцией данных по всем ревизиям, без обратной совместимости в коде.
- Матрица «станок × порода» — единственное разделоспецифичное представление. Остальные разделы получают три панели автоматически.
- Все цены и ставки в справочниках — без НДС. В форме есть переключатель «ввести с НДС», который пересчитывает значение при применении (ставка НДС — из `organization_rates`).
- Импорт из Excel — второй этап, после форм; в MVP — только кнопка-заглушка «скоро».

## 3. Целевой пользовательский процесс

1. Пользователь открывает «Справочники». Слева — разделы, сгруппированные по смыслу (Организация / Персонал / Техника / Материалы / Затраты юнита / Рынок), у каждого число записей; у раздела с ошибками валидации — счётчик предупреждений жёлтым.
2. Выбирает раздел — в центре список с колонками, специфичными для раздела (для должностей: Должность + категория, Операция, Оклад, Нормы, Сделка). Сегменты фильтра (Все / Прямые / Косвенные) и «Только активные». Изменённые в черновике строки отмечены жёлтой полосой слева.
3. Клик по строке открывает справа форму записи: поля сгруппированы (Постоянная часть / Сдельная часть / Прочее), у числовых — единица измерения, у ссылочных — селект, под полем — подсказка, что это значит для расчёта. Ошибка валидации — под конкретным полем.
4. «Применить» пишет в черновик; «Сбросить» возвращает запись к опубликованной версии. В шапке — «Черновик · N изменений».
5. Внизу списка — комментарий, «Проверить», «Отменить черновик», «Опубликовать ревизию N+1». Публикация возможна только без ошибок валидации.
6. Раздел «Условия бурения» открывается матрицей «станок × порода»: пустая ячейка — «по умолчанию», станок без нормы по умолчанию — красным. Клик по ячейке открывает ту же форму справа.

## 4. Границы MVP

### 4.1. Входит в MVP

- pydantic-схемы всех разделов из `Docs/REFERENCES_MODEL.md` (существующих и новых);
- эндпоинт схемы и валидация через схемы;
- миграция данных: новые разделы, переименование полей, перенос `drilling_productivity → drilling_conditions`;
- новый интерфейс: навигатор разделов, список, форма, матрица условий бурения, шапка со статусом черновика;
- вычисляемые подсказки для должностей и условий бурения;
- переключатель «ввести с НДС».

### 4.2. Не входит в MVP

- импорт из Excel (заглушка);
- история изменений записи и diff между ревизиями;
- права на отдельные разделы (остаётся `reference_editor` на всё);
- удаление Streamlit-версии справочников (`cost/references_ui.py`) — TASK-008;
- сам расчёт модели экономики — TASK-007.

## 5. Модель схемы

```python
# cost/v2/schemas/base.py
class ReferencePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

def RefField(section: str, *, description: str, optional: bool = False):
    """Ссылка на запись другого раздела: json_schema_extra={"x-ref": section}."""

def UnitField(unit: str, *, description: str, ge: float | None = 0, default=...):
    """Число с единицей измерения: json_schema_extra={"x-unit": unit}."""

# cost/v2/schemas/labor.py
class PositionPayload(ReferencePayload):
    category: Literal["DIRECT", "INDIRECT"]
    operation_code: str | None = RefField("operations", description="...", optional=True)
    norm_shifts_per_month: Decimal = UnitField("см", description="Нормативных смен в месяц")
    norm_operations_per_month: Decimal | None = UnitField("оп", description="...", default=None)
    piece_driver: Literal["rock_volume_m3", "explosive_kg", "drilling_m", "holes"] | None = None
    piece_unit: Decimal = Field(default=1, description="Расценка задаётся за столько единиц драйвера")
    per_diem_applies: bool = True

    @model_validator(mode="after")
    def _direct_needs_operation(self): ...
```

Реестр `SECTION_SCHEMAS: dict[str, type[ReferencePayload]]` — единственное место, где раздел связан со схемой. `REFERENCE_SECTION_DEFINITIONS` получает поле `ui`: `{"group": ..., "label": ..., "list_columns": [...], "view": "table" | "matrix"}`.

Ответ `GET /references/schema`:

```json
{
  "groups": [{"code": "labor", "label": "Персонал"}, ...],
  "sections": {
    "positions": {
      "label": "Должности и ставки",
      "group": "labor",
      "view": "table",
      "list_columns": ["name", "category", "operation_code", "fixed_monthly_rub", "norm_shifts_per_month", "piece_rate_rub"],
      "fieldsets": [{"title": "Постоянная часть", "fields": ["fixed_monthly_rub", "norm_shifts_per_month", "norm_operations_per_month"]}, ...],
      "json_schema": { ... pydantic model_json_schema() с x-unit / x-ref ... }
    }
  }
}
```

## 6. Файлы

Создать:

- `cost/v2/schemas/__init__.py` — `SECTION_SCHEMAS`, `section_schema_catalog()`
- `cost/v2/schemas/base.py`, `organization.py`, `labor.py`, `equipment.py`, `materials.py`, `sites.py`, `costs.py`, `market.py`
- `migrations/versions/20260902_0004_reference_schemas.py` — новые разделы, переименование полей, перенос `drilling_productivity`
- `api/schemas/reference_schema.py` — модели ответа `/references/schema`
- `frontend/src/pages/references/ReferencesPage.tsx` — каркас трёх панелей
- `frontend/src/pages/references/SectionNav.tsx`
- `frontend/src/pages/references/SectionList.tsx`
- `frontend/src/pages/references/RecordForm.tsx` — универсальная форма по JSON Schema
- `frontend/src/pages/references/fields/` — `NumberField.tsx`, `RefSelect.tsx`, `EnumSegment.tsx`, `DateField.tsx`, `BoolField.tsx`
- `frontend/src/pages/references/DrillingConditionsMatrix.tsx`
- `frontend/src/pages/references/PublishBar.tsx`
- `frontend/src/lib/referenceDerived.ts` — вычисляемые подсказки
- `frontend/src/types/referenceSchema.ts`
- `frontend/src/styles/references.css`
- `tests/test_reference_schemas.py`, `tests/test_api_reference_schema.py`
- `frontend/src/pages/references/__tests__/RecordForm.test.tsx`

Изменить:

- `cost/v2/references.py` — `REFERENCE_SECTION_DEFINITIONS` (+3 раздела, `ui`), `validate_reference_sections` через схемы
- `cost/v2/import_v1.py` — новые имена полей
- `api/routers/economics.py` — `GET /references/schema`
- `api/schemas/economics.py`
- `frontend/src/api/endpoints.ts`, `frontend/src/types/economics.ts`
- `frontend/src/app/AppShell.tsx` — пункт «Справочники project1» переименовать в «Справочники», старую страницу `EconomicsReferencesPage.tsx` удалить после переключения
- `scripts/seed_cost_v2.py` — сид новых разделов с примерами из `Docs/REFERENCES_MODEL.md`
- `README.md`, `CLAUDE.md`

## 7. Этапы реализации

### Этап A. Схемы и валидация (бэкенд)

1. `ReferencePayload`, `RefField`, `UnitField`; схемы всех разделов по таблицам `Docs/REFERENCES_MODEL.md`.
2. `SECTION_SCHEMAS` и `section_schema_catalog()`; `REFERENCE_SECTION_DEFINITIONS` дополнить `ui`.
3. `validate_reference_sections`: для каждой записи `SECTION_SCHEMAS[section].model_validate(payload)`; ошибки pydantic → `ValidationIssue(level="error", section, code, message, field=<имя поля>)`. Существующие перекрёстные проверки сохранить. Добавить проверку ссылок `x-ref` на существование записи в черновике.
4. Тесты: каждая схема принимает пример из `REFERENCES_MODEL.md` и отвергает лишнее поле (`extra="forbid"`), отрицательное число, `DIRECT` без `operation_code`.

### Этап B. Миграция данных

1. Alembic-миграция: пройти по всем ревизиям всех организаций, для каждого раздела применить переименование полей; `drilling_productivity` → `drilling_conditions` с `rock_code = null` (норма по умолчанию); создать пустые `organization_rates` с значениями из ADR (НДФЛ 13 %, взносы 30 %, НС 0,42 %, резерв 20 %, ОХР 10 %, рентабельность 10 %, НДС 20 %) для каждой организации.
2. Сухой прогон: миграция пишет отчёт «раздел → записей изменено» в лог и падает, если хоть один payload после переименования не проходит схему.
3. Обновить `seed_cost_v2.py` и `import_v1.py`.

### Этап C. Эндпоинт схемы

1. `GET /api/v1/economics/references/schema` — под `require_internal_access`; ответ кэшировать в процессе (схема статична).
2. Тест: у каждого раздела из `REFERENCE_SECTION_DEFINITIONS` есть `json_schema`, у каждого числового поля — `x-unit` или явное `x-unit: ""`.

### Этап D. Каркас интерфейса

1. `ReferencesPage`: грид `204px / 1fr / 344px` при ширине ≥ 1200; при меньшей форма открывается поверх списка как панель. Загрузка схемы и снимка параллельно; черновик хранится как сейчас (`DraftSections`), но без `payload_text`.
2. `SectionNav`: группы по `ui.group`, счётчики, предупреждения из последней валидации.
3. `SectionList`: колонки из `ui.list_columns`, форматирование по `x-unit`, теги для enum-полей, жёлтая полоса для изменённых записей, сегменты для первого enum-поля раздела, «Только активные».
4. `PublishBar`: комментарий, Проверить, Отменить черновик, Опубликовать; кнопка публикации заблокирована при ошибках.

### Этап E. Форма записи

1. `RecordForm`: по `fieldsets` из схемы; типы полей: number (+ единица), string, enum (сегмент ≤ 3 значений, иначе селект), boolean, date, ref (селект по записям раздела `x-ref` из черновика; недействующие записи серым).
2. Ошибки валидации — под полем; общие ошибки записи — над формой.
3. Вычисляемые подсказки из `referenceDerived.ts` для `positions` и `drilling_conditions`.
4. Переключатель «ввести с НДС» у полей с `x-unit` в рублях.
5. Действия: Применить / Сбросить / Деактивировать / Дублировать.

### Этап F. Матрица условий бурения

1. `DrillingConditionsMatrix`: строки — `equipment_types` с `kind = DRILL_RIG`, столбцы — «По умолчанию» + `rocks`; ячейка — запись `drilling_conditions` с этим станком и породой (с пометкой карьера, если задан `site_code`).
2. Переключатель «По породам / По карьерам / Списком».
3. Пустая ячейка → «Добавить норму» создаёт запись с предзаполненными `equipment_type_code` и `rock_code`.
4. Станок без записи с `rock_code = null` — красный статус, счётчик в шапке раздела.

### Этап G. Переключение и удаление старого

1. Пункт меню «Справочники» ведёт на новую страницу; старая `EconomicsReferencesPage.tsx` и `referenceRows.ts` удаляются.
2. README: раздел о справочниках; `CLAUDE.md`: правило «поля payload только через схемы, JSON в UI не показывать».

## 8. Критерии приёмки

- Ни на одном экране справочников нет поля с JSON.
- Все разделы из `REFERENCE_SECTION_DEFINITIONS` открываются в новом интерфейсе без разделоспецифичного кода, кроме `drilling_conditions`.
- Запись с лишним полем в payload не проходит валидацию с сообщением, называющим поле.
- У должности категории «Прямой» без операции публикация заблокирована, ошибка показана под полем «Операция пакета».
- Селект операции показывает только активные операции текущего черновика; выбранный код отображается тегом и названием.
- Подсказка «на один взрыв по нормативу» для примера 55 000 / 21 / 10 показывает 5 500 ₽ и 2,1 смены.
- Матрица условий бурения показывает 2 станка без нормы по умолчанию для сида, и после добавления нормы предупреждение исчезает без перезагрузки.
- Ввод 100 000 с включённым «с НДС» при ставке 20 % сохраняет 83 333,33.
- Миграция на копии production-базы проходит без ошибок валидации; `alembic downgrade` возвращает старые имена полей.
- Существующие тесты `tests/test_api_economics.py` проходят после переименования полей.
- Интерфейс на русском, единицы измерения у каждого числового поля.

## 9. Условия завершения

Задача закрыта, когда сметчик без подсказок разработчика может: добавить должность «Бурильщик» с нормативами и сделкой за п.м.; завести условие бурения для JK 830-3 на граните с уточнением по карьеру; увидеть, что у ТМ255-T нет нормы по умолчанию, и завести её; опубликовать ревизию с комментарием — и всё это без единого JSON-поля.
