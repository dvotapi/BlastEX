# Фикстуры контракта MagEX (наряд-путёвка, версия 1)

Копия каталога `MagEX/Docs/contracts/blastex/` (`fixtures/` и `naryad.v1.schema.json`)
из репозитория MagEX, `origin/main` `f9da761` (TASK-003 MagEX, PR 25). Не править:
при изменении контракта — скопировать заново.

- `keys/` — **тестовый** ключ MagEX (`kid` = `TEST-ONLY-magex-fixture`), закрытая часть
  общеизвестна; только тесты и локальный стенд (`BLASTEX_ALLOW_TEST_KEY=true`).
- `naryads/` — примеры содержимого (`*.json`) и подписанные строки (`*.jws`).
- `vectors/` — 19 строк и ожидаемый результат проверки (`index.json`).
