# TASK-008 — Единое хранилище PostgreSQL, отключение ML-слоя, удаление Streamlit

## Статус

- Приоритет: P1. Можно вести параллельно с TASK-006; завершить до релиза TASK-007.
- Статус требований: согласовано с владельцем (`Docs/ADR-001-economics-model.md`, «Сопутствующие изменения»).
- Обязательное условие: три независимых изменения — три отдельных PR в указанном порядке. Не смешивать с кодом модели экономики.

## 1. Контекст и цель

В репозитории сосуществуют: JSON-хранилище команд `data/teams/{id}/` (Cost V1), PostgreSQL-схема `blastex` (Cost V2, техпаспорта), Streamlit-интерфейс `app.py` с модулями `cost/*_ui.py`, и ML-слой `intelligence/` с девятью роутерами. Целевая эксплуатация — много организаций и пользователей, поэтому файлы по `team_id` без изоляции и версий недопустимы; Streamlit больше не поддерживается; ML-слой не входит в ближайший релиз.

Цель: одно хранилище (PostgreSQL, обязательный `BLASTEX_DATABASE_URL`), один интерфейс (React), ML-слой за фича-флагом с кодом на месте.

## 2. Принятые решения

- `BLASTEX_DATABASE_URL` становится обязательным; без него приложение не стартует. Ветка «Cost V1 на файлах, `/economics/*` → 503» удаляется.
- Данные `data/teams/*.json` импортируются в PostgreSQL одним скриптом (расширенный `import_cost_v1_to_project1.py`) при развёртывании; после проверки каталог удаляется из Docker volume.
- `organization_id` обязателен во всех таблицах схемы `blastex`; репозиторий фильтрует по нему в каждом запросе; RLS — отдельной задачей позже.
- ML-слой отключается флагом `BLASTEX_INTELLIGENCE_ENABLED` (по умолчанию `false`): роутеры `datasets`, `calibration`, `outcomes`, `learning`, `registry`, `drift`, `spatial`, `recommendation`, `optimization` регистрируются только при `true`; при `false` их пути возвращают 501 с сообщением «Модуль отключён». Код `intelligence/` и `design/optimization` не удаляется.
- Streamlit удаляется целиком: `app.py`, `cost/*_ui.py`, `cost/references_store.py`, `cost/persistence_ui.py`, `.streamlit/`, файл `Streamlit`, зависимости `streamlit`, `altair`, `pydeck`, `watchdog`, `GitPython`. `max_bot.py` остаётся, если не зависит от Streamlit (проверить).
- Cost V1 (`cost/strategies/`, `cost/engine.py`, `cost/persistence.py`) остаётся до завершения TASK-007, затем отдельным решением.

## 3. Этапы реализации

### PR 1. PostgreSQL обязателен

1. `api/main.py`, `cost/v2/db_repository.py`: при пустом `BLASTEX_DATABASE_URL` — ошибка запуска с понятным текстом. Удалить `InMemoryEconomicsRepository` из production-пути (оставить только для тестов).
2. Проверить `organization_id` во всех таблицах: `reference_revisions`, `economic_scenarios`, `calculation_runs`, `technical_passports`, `mass_blast_projects` и т.д. Где нет — миграция с backfill из единственной организации.
3. Все методы репозитория принимают `organization_id` первым аргументом и включают его в `WHERE`; тест, который проверяет, что данные одной организации не видны другой.
4. `scripts/import_cost_v1_to_project1.py`: перенос сценариев и справочников V1 в V2 (после TASK-006 — в новые имена полей). Сухой прогон по умолчанию, `--publish` для записи.
5. `docker-compose.yml`: сервис `postgres` (или внешний URL), `alembic upgrade head` до старта API уже есть — проверить. Volume `blastex_data` больше не монтируется в `/app/data` после миграции.
6. README: раздел «Быстрый старт» без варианта «без БД».

### PR 2. Фича-флаг ML-слоя

1. `api/config.py` (или где живут настройки): `intelligence_enabled: bool = False` из `BLASTEX_INTELLIGENCE_ENABLED`.
2. `api/main.py`: условная регистрация роутеров; при отключении — единый обработчик, отдающий 501 для префиксов `/api/v1/{datasets,calibration,outcomes,learning,registry,drift,spatial,recommendation,optimization}`.
3. `GET /api/v1/features` → `{"intelligence": false, ...}`; фронт скрывает разделы проектирования BDX-011…BDX-023 и пункты меню по этому ответу.
4. Тесты `tests/test_api_{datasets,calibration,outcomes,learning,registry,drift,spatial,recommendation,optimization}.py` — `pytest.mark.skipif(not intelligence_enabled)` через фикстуру, которая включает флаг для этих файлов; плюс тест, что при выключенном флаге пути дают 501.
5. README и `Docs/BlastEX_Design_Simulation_Intelligence_Roadmap.md`: пометка «отключено флагом».

### PR 3. Удаление Streamlit

1. Удалить файлы из §2; убрать импорты `streamlit` во всём дереве (`grep -rn "import streamlit\|from streamlit"`).
2. `cost/references_store.py` использовался движком V1 для чтения справочников из `session_state` — заменить чтением из репозитория V2 или удалить вместе с зависящим кодом, если он не нужен фронту.
3. `requirements.txt`: оставить только то, что импортирует `api/`, `cost/`, `design/`, `simulation/`, `intelligence/`, `max_bot.py`; `requirements-api.txt` объединить с `requirements.txt`.
4. `Dockerfile`: без Streamlit-слоя; проверить размер образа.
5. `.github/workflows/deploy.yml`: убрать шаги Streamlit, если есть.
6. README: удалить раздел «Резервный интерфейс (Streamlit)», обновить структуру проекта; `CLAUDE.md`: «Streamlit удалён, UI — только `frontend/`».

## 4. Критерии приёмки

- Приложение не стартует без `BLASTEX_DATABASE_URL` и говорит об этом одной строкой.
- Тест изоляции организаций проходит для всех репозиторных методов.
- `data/teams` не читается нигде в коде (`grep -rn "data/teams"` пуст, кроме скрипта импорта).
- При `BLASTEX_INTELLIGENCE_ENABLED=false` все девять префиксов дают 501, фронт не показывает соответствующих разделов; при `true` — прежнее поведение и прежние тесты.
- `pip install -r requirements.txt` не тянет `streamlit`; `grep -rn streamlit` по коду пуст.
- Docker-образ собирается и проходит health-check; `docker compose up` поднимает postgres + api + web.
- Все тесты, не относящиеся к ML-слою, проходят.

## 5. Условия завершения

Задача закрыта, когда свежее развёртывание по README поднимается на пустой PostgreSQL, импорт переносит данные существующей организации, интерфейс — только React, а ML-разделы можно включить одной переменной окружения без изменения кода.
