-- Права роли blastex на схему public базы project1.
--
-- Кто и когда запускает: администратор базы (суперпользователь либо
-- владелец схемы public) в базе project1, один раз перед первым включением
-- обмена на странице «Справочники» — до этого переключатели обмена и
-- зеркал показывают текст ошибки базы, а публикация ревизий работает как
-- раньше, без записи в public. Повторный запуск безопасен: скрипт
-- идемпотентен (GRANT переиздаётся без ошибки, политики создаются только
-- если их ещё нет).
--
-- Что скрипт НЕ делает: не создаёт зеркала public.blastex_<раздел> и не
-- ставит для них политику blastex_full_access — это делает само приложение
-- при первом включении зеркала раздела (см. cost/v2/public_sync/mirror.py),
-- вместе с ENABLE ROW LEVEL SECURITY и CREATE POLICY на только что созданной
-- таблице. Здесь идёт речь только о существующих таблицах журнала project1.
--
-- Список таблиц ниже должен дословно совпадать с константой TABLES из
-- cost/v2/public_sync/mapping.py (13 таблиц) — это проверяет тест
-- tests/test_grant_script.py. Прав DELETE роль blastex не получает нигде:
-- обмен только читает и дописывает записи, не удаляет их. На прочие таблицы
-- схемы public (в них персональные и банковские данные) права не выдаются:
-- строк этих таблиц роль blastex не увидит. Исключение — последовательности:
-- USAGE, SELECT выдаётся сразу на все последовательности схемы (иначе INSERT
-- не получит следующий id); данных таблиц это не раскрывает, из
-- последовательности видно только её счётчик.

GRANT USAGE, CREATE ON SCHEMA public TO blastex;

-- Таблицы cost.v2.public_sync.mapping.TABLES, в порядке константы.
GRANT SELECT, INSERT, UPDATE ON public.counterparties TO blastex;
GRANT SELECT, INSERT, UPDATE ON public.sites TO blastex;
GRANT SELECT, INSERT, UPDATE ON public.machine_types TO blastex;
GRANT SELECT, INSERT, UPDATE ON public.equipment_models TO blastex;
GRANT SELECT, INSERT, UPDATE ON public.equipment_units TO blastex;
GRANT SELECT, INSERT, UPDATE ON public.initiating_device_types TO blastex;
GRANT SELECT, INSERT, UPDATE ON public.delay_series TO blastex;
GRANT SELECT, INSERT, UPDATE ON public.tool_types TO blastex;
GRANT SELECT, INSERT, UPDATE ON public.tools_inventory TO blastex;
GRANT SELECT, INSERT, UPDATE ON public.explosive_material_prices TO blastex;
GRANT SELECT, INSERT, UPDATE ON public.explosive_spec_items TO blastex;
GRANT SELECT, INSERT, UPDATE ON public.explosive_purchase_specs TO blastex;
GRANT SELECT, INSERT, UPDATE ON public.contracts TO blastex;

-- Последовательности (id serial/identity) нужны для чтения текущего значения
-- при INSERT без явного id. Права идут на все последовательности схемы, а не
-- только на 13 таблиц: отдельные имена последовательностей PostgreSQL
-- порождает сам, и промах оставил бы вставку без nextval. Данные прочих
-- таблиц так не раскрываются — в последовательности лежит только счётчик.
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO blastex;

-- Политики RLS полного доступа для blastex на тех же 13 таблицах. В
-- project1 включён событийный триггер public.rls_auto_enable — он сам
-- включает RLS на каждой новой таблице public, а на существующих таблицах
-- RLS уже включён, поэтому без политики роль blastex не увидит ни одной
-- строки. Блок идемпотентен: политика создаётся только если её ещё нет.
DO $$
DECLARE
    tbl text;
BEGIN
    FOREACH tbl IN ARRAY ARRAY[
        'counterparties',
        'sites',
        'machine_types',
        'equipment_models',
        'equipment_units',
        'initiating_device_types',
        'delay_series',
        'tool_types',
        'tools_inventory',
        'explosive_material_prices',
        'explosive_spec_items',
        'explosive_purchase_specs',
        'contracts'
    ]
    LOOP
        IF NOT EXISTS (
            SELECT 1 FROM pg_policies
            WHERE schemaname = 'public'
              AND tablename = tbl
              AND policyname = 'blastex_full_access'
        ) THEN
            EXECUTE format(
                'CREATE POLICY blastex_full_access ON public.%I FOR ALL TO blastex USING (true) WITH CHECK (true)',
                tbl
            );
        END IF;
    END LOOP;
END $$;
