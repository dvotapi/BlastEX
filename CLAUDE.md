# CLAUDE.md

Инструкции для Claude Code при работе с этим репозиторием.

## Язык общения

Всегда общайся с пользователем на русском языке.

## Справочники экономики (Cost V2)

Поля payload описываются только схемами в `cost/v2/schemas/`: единица
измерения — `x-unit`, ссылка на другой раздел — `x-ref`, короткая подпись
поля — `title`, пояснение — `description`. Новый раздел добавляется схемой,
записью в `SECTION_SCHEMAS` и в `REFERENCE_SECTION_DEFINITIONS`.

Интерфейс строит формы по каталогу схем и не хранит собственных знаний о
полях: не заводи разделоспецифичных компонентов (единственное исключение —
матрица условий бурения) и не показывай пользователю JSON — ни в поле ввода,
ни в подсказке.

## Модель себестоимости блока (TASK-007)

Нормы живут только в `cost/model/`, цены — только в справочниках. Новая
статья вида «цена × существующий драйвер» — это запись в `cost_rules`, а не
код; код нужен лишь для нового типа натуральной величины.

Отсутствующая запись справочника даёт предупреждение и нулевую строку, а не
исключение. Постоянные затраты юнита распределяются по плановому объёму
юнита, постоянные затраты техники — по её плановым сменам; оба плана —
параметры вкладки. Подробности — `Docs/COST_MODEL.md`.

## Модель подбора q (Kuz-Ram)

Лист «Расчёт» подбирает q по Каннингему: формулы —
`simulation/fragmentation/cunningham.py`, подбор — `Blast.py::optimize_blast`,
окно «Модель Kuz-Ram» — `frontend/src/pages/calc/kuzram/`.
Прогноз одной точки собирает `cunningham.predict_point` — единственное место,
где формулы складываются вместе. Движок «Проектирования»
(`simulation/fragmentation/engine.py`) зовёт её во всех трёх моделях через
`simulation/fragmentation/base.py::region_point`; прежние формулы —
`simulation/fragmentation/legacy/` под именами `*_legacy`. Настройки модели
«Проектирование» берёт из объекта работ
(`api/services/fragmentation_settings.py`). ML-калибровки и пространственные
признаки до PR 3 считают базу старой моделью `kuzram_legacy`; подробности —
`Docs/KUZRAM_MODEL.md`.

## Импорт чертежа маркшейдера (TASK-013)

Окно «Импорт чертежа» (`frontend/src/pages/design/cadImport/`) читает DXF/DWG
целиком и раскладывает сущности по ролям. Чтение и роли —
`design/spatial/cad/`, хранение — таблицы `cad_*`, API — `/design/cad`
(не `/spatial`: это ML-роутер, на проде он выключен). `$INSUNITS` не
масштабирует чертёж: масштаб 0,001 только предлагается по размеру. Шаблон
«имя слоя → роль» хранится на объекте (`site_code`). Контур блока (PR 2) — `design/spatial/cad/` (`rings`,
`stitch`, `contour`, `two_contours`, shapely ≥ 2), предпросмотр —
`POST /design/cad/sources/{id}/contour`; в паспорте — `contour.cad`, ключ
пишется только когда поле есть (иначе сменится хэш утверждённых паспортов).
Кровля (PR 3) — `design/spatial/cad/surface*.py`: CDT через PythonCDT
(запасной путь scipy — `BLASTEX_SURFACE_BUILDER`), предпросмотр —
`POST /design/cad/sources/{id}/surface`. Длина скважины — одна формула
L = (S − Z)/cos α + Δ (`geometry.hole_depth_m`), пересчёт —
`design/hole_recompute.py` и `POST /design/holes/recompute`; `surfaces.top.cad`,
`Hole.manual` и `contour.cad.map_volume_m3` пишутся только когда заданы.
Ситуация и СК (PR 4) — `design/spatial/cad/situation.py`, `crs.py`,
`api/services/cad_situation_service.py`: серии источников по названию, вид
объектов слоя, СК объекта в `cad_site_settings`, в паспорте —
`contour.cad.situation` и `coordinate_system.height_system` (только когда
заданы); на странице — `useSituation`, подложка `SituationCanvas`, группа
«Ситуация» в «Виде». Базовый слой холста окна — `<canvas>` (`CanvasHitIndex`).
Подробности — `Docs/CAD_IMPORT.md`; справка «?» окна обновляется в каждом PR
задачи.

## Интерфейс

Streamlit удалён: UI — только `frontend/` (React + TypeScript). Расчётные
модули не знают об интерфейсе; всё, что нужно фронту, проходит через
`api/`.

Справочники Cost V1 (породы, ВМ, станки, объекты, номенклатура, постоянные
расходы, должности) читаются из опубликованной ревизии V2 через
`cost/v2/legacy_adapter.py`; файловых справочников нет. Каталог `data/teams`
хранит только паспорта проектирования и артефакты ML.
