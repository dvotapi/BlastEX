#!/usr/bin/env bash
# Forced command ключа деплоя GitHub Actions на production VPS.
#
# Устанавливается в /usr/local/sbin/deploy-blastex (README, раздел 7): sshd
# запускает его вместо любой команды, пришедшей с ключом, а саму команду
# кладёт в SSH_ORIGINAL_COMMAND. Workflow передаёт в ней SHA коммита, чьи
# тесты прошли в прогоне, и выкатывается ровно он, а не последний main: пока
# прогон шёл, в main мог попасть коммит с падающим тестом.
#
# Коды выхода: 65 — коммит отклонён, повтор не поможет, и workflow его не
# повторяет; 75 — идёт другое развёртывание; 128 — не удался git fetch
# (GitHub временно ограничивает анонимные скачивания), workflow повторяет.
set -euo pipefail
# Диапазон [0-9a-f] в регулярном выражении однозначен только в локали C, а
# клиент SSH может передать свою через LANG/LC_*.
export LC_ALL=C

APP_DIR="${APP_DIR:-/root/complex-services-web/blastex}"
LOCK_FILE="${DEPLOY_LOCK_FILE:-/var/lock/blastex-deploy.lock}"
# Последний успешно выкаченный коммит. HEAD для этого не годится: он
# переключается до сборки и остаётся на коммите, чья сборка упала.
DEPLOYED_REF=refs/deploy/production
REJECTED=65
BUSY=75

reject() {
  echo "ERROR: $*" >&2
  exit "$REJECTED"
}

self="${BASH_SOURCE[0]}"
[[ "$self" == /* ]] || self="$PWD/$self"

sha="${SSH_ORIGINAL_COMMAND:-}"
if [[ ! "$sha" =~ ^[0-9a-f]{40}$ ]]; then
  reject "ожидается полный SHA коммита (40 символов 0-9a-f), получено: $(printf '%q' "$sha")"
fi

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "ERROR: идёт другое развёртывание ($LOCK_FILE)" >&2
  exit "$BUSY"
fi

cd "$APP_DIR"

git fetch origin +refs/heads/main:refs/remotes/origin/main

if ! git merge-base --is-ancestor "$sha" refs/remotes/origin/main 2>/dev/null; then
  reject "коммит $sha не входит в origin/main"
fi

# Прогоны в concurrency-группе не обязаны идти по порядку, а перезапуск
# старого прогона присылает его SHA. Коммит, уже вошедший в выкаченный, —
# это откат; его делают revert-коммитом в main, а не повтором прогона. Тот
# же коммит выкатывается повторно: так ручной запуск пересобирает прод.
deployed="$(git rev-parse -q --verify "$DEPLOYED_REF^{commit}" || true)"
if [[ -n "$deployed" && "$sha" != "$deployed" ]] \
  && git merge-base --is-ancestor "$sha" "$deployed"; then
  reject "коммит $sha старше выкаченного $deployed и уже входит в него; откат — revert-коммитом в main"
fi

# Правка отслеживаемого файла на сервере перенеслась бы в сборку, и на прод
# ушёл бы не проверенный коммит.
modified="$(git status --porcelain --untracked-files=no)"
if [[ -n "$modified" ]]; then
  printf '%s\n' "$modified" >&2
  reject "в $APP_DIR изменены отслеживаемые файлы, выкатить ровно $sha нельзя"
fi

git checkout --quiet --detach "$sha"

ahead="$(git rev-list --count "$sha..refs/remotes/origin/main")"
echo "Разворачиваю $(git log -1 --format='%h %s')"
if [[ "$ahead" -gt 0 ]]; then
  echo "origin/main ушёл дальше (новых коммитов: $ahead) — их выкатит следующий прогон, когда пройдут его тесты"
fi

# Эта копия ставится на сервер вручную, поэтому правка в репозитории сама до
# сервера не доходит.
if [[ -f scripts/deploy_forced_command.sh ]] && ! cmp -s "$self" scripts/deploy_forced_command.sh; then
  echo "WARNING: $self отличается от scripts/deploy_forced_command.sh в $sha — переустановите его (README, раздел 7)" >&2
fi

./scripts/deploy_vps.sh
git update-ref "$DEPLOYED_REF" "$sha"
