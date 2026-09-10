# Основное ВВ в смете берётся из паспорта

## Контекст

Вкладка «Экономика блока» подставляет в строку 1.1 «Взрывчатые материалы»
первую позицию каталога с ценой — на проде это «ГВВ Гранулит РП». Паспорт при
этом посчитан на другом веществе: в «Блок 4 · вер. 1» выбран ЭВЕРСИН. Сметчик
получает смету на не том ВВ и замечает подмену, только если сверит строку с
паспортом вручную.

Цена ошибки на этом блоке: 25 989 кг ВВ на 30 000 м³, разница цен Гранулита
(46,00 ₽/кг) и Эверсина (48,90 ₽/кг) — 75 369 ₽ на блок, 2,51 ₽/м³.
Себестоимость показана 107,19 ₽/м³ вместо 109,70 — занижена на 2,3 % молча.

Причина разобрана владельцем и перепроверки не требует:

1. `_default_nomenclature` (`api/routers/block_economics.py:454`) для каждой
   роли берёт первую ценовую позицию каталога; паспорт учитывается только у
   скважинных НСИ — там позиция подбирается по требуемой длине.
2. Паспорт несёт выбранное ВВ подписью диаграммы: `selected_variant.label`
   вида «ЭВЕРСИН», «ГРАНУЛИТ-РП», «ПОРЭМИТ» (`chart_label` расчётной части →
   `api/services/blast_service.py:91` → `BlastGeometryResponse.label` →
   `frontend/src/pages/CalcPage.tsx:164`). Это не код и не полное имя.
3. В каталоге каждое ВВ лежит дважды: ценовая позиция `MAT_VV_*` из
   номенклатуры и бесценовой дубль `EXP_*` из справочника расчётной части.
   Простое совпадение по имени попало бы в нулевой дубль и дало бы нулевую
   строку с предупреждением — тот же класс проблемы, что дубль «Искра-П-*-5».

## Что уже решено с владельцем

1. **Подбор — сопоставлением подписи паспорта с ценовыми позициями каталога**
   по нормализованному имени. Нормализация снимает то, чем расходятся два
   справочника: регистр, префиксы типа ВВ («ЭВВ», «ГВВ», «ПЭВВ», «ПВВ»),
   суффиксы марки («-100», «Э-100»), пробелы и дефисы.
2. **Откат обязателен.** Нет совпадения, нет подписи, старый паспорт — работает
   прежнее правило: первая ценовая позиция. Ни исключения, ни пустого
   умолчания.
3. **Позиция без цены умолчанием не становится ни при каком совпадении.**
4. **Меняется только роль `EXPLOSIVE`.** Подбор скважинных НСИ по длине и
   остальные роли не трогаются.
5. **Не входит в работу** (назвать в отчёте, делать по отдельному решению):
   код номенклатуры в паспорте вместо подписи диаграммы; чистка дублей `EXP_*`
   в справочнике.

## Ограничения

- Фронт, схемы API и модель себестоимости (`cost/`, `frontend/`) не меняются:
  умолчание приходит в `parameters.nomenclature` ответа `/model-defaults`.
- Правило подбора живёт в `_default_nomenclature`; паспорт там уже есть
  вторым аргументом.
- `pytest tests/test_api_block_economics.py` зелёный после каждой задачи;
  полный `pytest` — перед PR.

---

## Задача 1. Нормализация имени ВВ и подбор умолчания

**Файлы:**
- Изменить: `api/routers/block_economics.py` (рядом с `_default_nomenclature:454`)
- Изменить: `tests/model_fixtures.py` (бесценовые дубли ВВ, как на проде)
- Тесты: `tests/test_api_block_economics.py` (рядом с существующими на
  `model-defaults`)

**Фикстуры.** Сейчас роль `EXPLOSIVE` в тестах — «Гранулит» (`MAT_ANFO`, 45 ₽),
«ЭВВ Эверсин-100» (`MAT_EVERSIN`, 48,90 ₽) и «ЭВВ Протолит-100`
(`MAT_PROTOLIT`, без цены). Первой ценовой по алфавиту идёт «Гранулит», это и
есть нынешнее умолчание. Добавляются два бесценовых дубля, повторяющих прод:
`EXP_PEVV_EVERSIN_E_100` «Эверсин Э-100» и `EXP_PVV_GRANULIT_RP`
«Гранулит-РП». Цен у них нет, поэтому нынешнее умолчание фикстур не меняется
и существующие тесты остаются в силе.

- [ ] **Шаг 1: Написать падающие тесты**

```python
def _passport_with_variant(repository, label: str) -> str:
    passport = repository.save_technical_passport(
        "default",
        "tester",
        site_code="SITE_MAIN",
        object_name=f"Блок на {label}",
        previous_passport_id=None,
        reference_revision_id=repository.list_reference_revisions("default")[0].id,
        formula_version="blast-geometry-v1",
        input_snapshot={},
        selected_variant={"label": label},
        block_snapshot={},
        physical={key: str(value) for key, value in fx.physical().items()},
        lineage={},
    )
    return passport.id


def _explosive_default(test_client, passport_id: str) -> str:
    body = test_client.get(
        "/api/v1/economics/model-defaults",
        params={"technical_passport_id": passport_id, "package_code": "DRILL_AND_BLAST"},
    ).json()
    return body["parameters"]["nomenclature"]["EXPLOSIVE"]


def test_explosive_default_follows_the_passport_variant(client) -> None:
    """Смета считается на том ВВ, на котором посчитан блок, а не на первом в каталоге."""

    test_client, repository, _ = client

    # Подпись паспорта — подпись диаграммы: без слова типа ВВ, в другом
    # регистре, с дефисами, иногда с маркой.
    eversin = _passport_with_variant(repository, "ЭВЕРСИН")
    granulit = _passport_with_variant(repository, "ГРАНУЛИТ-РП")
    marked = _passport_with_variant(repository, "ЭВЕРСИН Э-100")

    assert _explosive_default(test_client, eversin) == "MAT_EVERSIN"
    assert _explosive_default(test_client, granulit) == "MAT_ANFO"
    assert _explosive_default(test_client, marked) == "MAT_EVERSIN"


def test_explosive_default_skips_the_priceless_twin(client) -> None:
    """Дубль из справочника расчётной части совпадает по имени, но цены не имеет."""

    test_client, repository, _ = client

    chosen = _explosive_default(test_client, _passport_with_variant(repository, "ЭВЕРСИН"))

    assert chosen == "MAT_EVERSIN"
    assert chosen != "EXP_PEVV_EVERSIN_E_100"


def test_explosive_default_falls_back_when_the_variant_is_unknown(client) -> None:
    """Подписи нет в каталоге — прежнее правило, а не пустая строка сметы."""

    test_client, repository, passport_id = client

    unknown = _passport_with_variant(repository, "ПОРЭМИТ 1А")

    assert _explosive_default(test_client, unknown) == "MAT_ANFO"
    # Старый паспорт без выбранного варианта ведёт себя как прежде.
    assert _explosive_default(test_client, passport_id) == "MAT_ANFO"
```

- [ ] **Шаг 2: Убедиться, что тесты падают**

Запуск: `pytest tests/test_api_block_economics.py -k explosive_default -v`
Ожидание: FAIL — `MAT_ANFO` вместо `MAT_EVERSIN` в первых двух тестах,
третий проходит (это прежнее поведение).

- [ ] **Шаг 3: Добавить дубли в фикстуры**

`tests/model_fixtures.py`, в `MATERIALS` рядом с прочими ВВ:

```python
    # Дубли из справочника ВВ расчётной части: имена те же, цен нет.
    item(
        "EXP_PEVV_EVERSIN_E_100",
        "Эверсин Э-100",
        {"unit": "KG", "material_kind": "ВВ", "storage_class": "BULK", "nomenclature_role": "EXPLOSIVE"},
    ),
    item(
        "EXP_PVV_GRANULIT_RP",
        "Гранулит-РП",
        {"unit": "KG", "material_kind": "ВВ", "storage_class": "BULK", "nomenclature_role": "EXPLOSIVE"},
    ),
```

- [ ] **Шаг 4: Написать подбор**

`api/routers/block_economics.py`, перед `_default_nomenclature` (плюс `import re` в шапке):

```python
# Слова типа ВВ в номенклатуре: справочник расчётной части их не пишет.
_EXPLOSIVE_KIND_WORDS = frozenset({"вв", "эвв", "гвв", "пвв", "пэвв"})


def _explosive_key(text: str) -> str:
    """Имя ВВ без того, чем расходятся два справочника.

    Номенклатура зовёт вещество «ЭВВ Эверсин-100», паспорт несёт подпись
    диаграммы «ЭВЕРСИН» или «ЭВЕРСИН Э-100». Общее у записей — само название,
    поэтому из имени убираются регистр, знаки, слово типа ВВ и обозначение
    марки: части с цифрами («100», «1А») и одиночные буквы («Э»).
    """

    tokens = [
        token
        for token in re.split(r"[^0-9a-zа-я]+", str(text).casefold().replace("ё", "е"))
        if token
    ]
    kept = [
        token
        for token in tokens
        if token not in _EXPLOSIVE_KIND_WORDS
        and len(token) > 1
        and not any(char.isdigit() for char in token)
    ]
    return "".join(kept)


def _explosive_from_variant(
    options: Sequence[dict[str, Any]], passport: StoredTechnicalPassport
) -> str:
    """Ценовая позиция каталога, отвечающая выбранному в паспорте ВВ.

    Пустая строка означает «совпадения нет» — тогда работает прежнее правило
    первой ценовой позиции: подпись бывает старой, пустой или отсутствующей
    в номенклатуре, и смета всё равно должна собраться.
    """

    # Снимок варианта — свободный JSON клиента: подписи может не быть вовсе,
    # а `str(None)` дал бы ключ «none» и случайное совпадение.
    label = passport.selected_variant.get("label")
    key = _explosive_key(label) if isinstance(label, str) else ""
    if not key:
        return ""

    exact: list[dict[str, Any]] = []
    partial: list[dict[str, Any]] = []
    for row in options:
        if row["price_rub"] <= 0:
            continue
        name_key = _explosive_key(row["name"])
        if not name_key:
            continue
        if name_key == key:
            exact.append(row)
            continue
        longer, shorter = (
            (name_key, key) if len(name_key) >= len(key) else (key, name_key)
        )
        # Четыре знака — чтобы «ЭВ» или «РП» не притянули чужое вещество.
        if len(shorter) >= 4 and longer.startswith(shorter):
            partial.append(row)

    candidates = exact or partial
    if not candidates:
        return ""
    # Ближе к подписи то, что меньше расходится с ней длиной: у подписи
    # «Гранулит РП новый» это «Гранулит РП», а не «Гранулит». Имя добивает
    # порядок, чтобы умолчание не зависело от порядка обхода справочника.
    return min(
        candidates,
        key=lambda row: (abs(len(_explosive_key(row["name"])) - len(key)), row["name"]),
    )["code"]
```

В `_default_nomenclature`, после общего цикла по ролям и рядом с веткой
`NSI_DOWNHOLE`:

```python
    explosive = _explosive_from_variant(catalog.get("EXPLOSIVE", ()), passport)
    if explosive:
        chosen["EXPLOSIVE"] = explosive
```

Докстринг `_default_nomenclature` дополняется строкой: основное ВВ идёт от
паспорта, остальные роли — первой ценовой позицией.

- [ ] **Шаг 5: Убедиться, что тесты проходят**

Запуск: `pytest tests/test_api_block_economics.py -v`
Ожидание: PASS, включая прежние тесты умолчаний и подбора НСИ по длине.

- [ ] **Шаг 6: Полный прогон и коммит**

```bash
pytest -q
git add api/routers/block_economics.py tests/model_fixtures.py tests/test_api_block_economics.py
git commit -m "feat(economics): умолчание ВВ из паспорта, а не первое в каталоге"
```

---

## Задача 2. Документация правила

**Файлы:**
- Изменить: `Docs/BLOCK_ECONOMICS_UI.md` (раздел про умолчания номенклатуры)

- [ ] **Шаг 1: Дописать правило**

Одним абзацем: умолчание роли `EXPLOSIVE` подбирается по
`selected_variant.label` паспорта сопоставлением нормализованных имён (снимаются
регистр, префикс типа ВВ, пробелы, дефисы и марка), только среди позиций с
ценой; при отсутствии совпадения — первая ценовая позиция, как у прочих ролей.
Там же — что подпись приходит из `chart_label` расчётной части, поэтому
сопоставление идёт по имени, а не по коду.

- [ ] **Шаг 2: Коммит**

```bash
git add Docs/BLOCK_ECONOMICS_UI.md
git commit -m "docs: правило подбора ВВ по паспорту на вкладке экономики"
```

---

## Проверка

- `pytest tests/test_api_block_economics.py` — прежние тесты умолчаний и три
  новых на подбор ВВ.
- `pytest -q` — весь набор: правило меняет ответ `/model-defaults`, которым
  пользуются тесты вариантов и экспорта.
- Фронт не менялся, `npm --prefix frontend test` прогоняется один раз для
  подтверждения.
- После слияния — прод `https://blastex.complex-services.ru/`, вкладка
  «Экономика», паспорт «Блок 4 · вер. 1»: строка 1.1 показывает Эверсин,
  себестоимость 109,70 ₽/м³ вместо 107,19.

## Документация и процесс

- План лежит в `Docs/plans/2026-09-10-explosive-default-from-passport.md`.
- `Docs/BLOCK_ECONOMICS_UI.md` дополняется правилом подбора (задача 2).
- Ветка `feat/explosive-default-from-passport` от `origin/main`, ревью через
  `/code-review` до PR (правило проекта), слияние сквошем по команде владельца.
