"""Тесты деплоя, привязанного к проверенному коммиту.

Forced command ``scripts/deploy_forced_command.sh`` запускается так же, как
на сервере, но над временными репозиториями: голый ``origin`` вместо GitHub и
его клон вместо ``/root/complex-services-web/blastex``. Вместо
``scripts/deploy_vps.sh`` в клоне лежит заглушка: она записывает коммит, на
котором её запустили, и завершается с заданным кодом. Так проверяется
главное — выкатывается ровно коммит из ``SSH_ORIGINAL_COMMAND``, а не
последний ``main``.

Шаг деплоя из ``.github/workflows/deploy.yml`` исполняется целиком с
поддельным ``ssh``: он записывает аргументы и отвечает заданными кодами.
"""
from __future__ import annotations

import fcntl
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "deploy_forced_command.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "deploy.yml"

REJECTED = 65
BUSY = 75
DEPLOYED_REF = "refs/deploy/production"

DEPLOY_STUB = """#!/bin/sh
git rev-parse HEAD >> "$STUB_LOG"
exit "${STUB_EXIT:-0}"
"""

# Замена util-linux flock там, где его нет (macOS). Понимает только
# `flock -n FD` — так его вызывает скрипт. Блокировка ставится на
# унаследованный дескриптор и держится, пока он открыт у вызвавшей
# оболочки, как у настоящего flock.
FLOCK_SHIM = """#!/usr/bin/env python3
import fcntl, sys
if len(sys.argv) != 3 or sys.argv[1] != "-n":
    sys.exit("flock shim: supported only `flock -n FD`")
try:
    fcntl.flock(int(sys.argv[2]), fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    sys.exit(1)
"""

FAKE_SSH = """#!/usr/bin/env python3
import json, os, sys
calls = os.environ["FAKE_SSH_CALLS"]
with open(calls, "a", encoding="utf-8") as fh:
    fh.write(json.dumps(sys.argv[1:]) + "\\n")
with open(calls, encoding="utf-8") as fh:
    attempt = sum(1 for _ in fh)
codes = os.environ["FAKE_SSH_CODES"].split()
sys.exit(int(codes[min(attempt, len(codes)) - 1]))
"""


def _write_executable(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)


def _isolated_env(home: Path) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("GIT_") and key != "SSH_ORIGINAL_COMMAND"
    }
    env.update(
        HOME=str(home),
        XDG_CONFIG_HOME=str(home / ".config"),
        GIT_CONFIG_NOSYSTEM="1",
        GIT_AUTHOR_NAME="Test",
        GIT_AUTHOR_EMAIL="test@example.com",
        GIT_COMMITTER_NAME="Test",
        GIT_COMMITTER_EMAIL="test@example.com",
    )
    return env


class Stand:
    """``origin``, клон разработчика ``seed`` и клон сервера ``app``."""

    def __init__(self, tmp_path: Path) -> None:
        self.tmp = tmp_path
        self.origin = tmp_path / "origin.git"
        self.seed = tmp_path / "seed"
        self.app = tmp_path / "app"
        self.log = tmp_path / "deployed.log"
        self.lock = tmp_path / "deploy.lock"
        self.env = _isolated_env(tmp_path / "home")
        (tmp_path / "home").mkdir()
        if shutil.which("flock") is None:
            _write_executable(tmp_path / "bin" / "flock", FLOCK_SHIM)
            self.env["PATH"] = f"{tmp_path / 'bin'}{os.pathsep}{self.env['PATH']}"

        self.git(tmp_path, "init", "-q", "--bare", "--initial-branch=main", str(self.origin))
        self.git(tmp_path, "init", "-q", "--initial-branch=main", str(self.seed))
        self.git(self.seed, "remote", "add", "origin", str(self.origin))
        self.initial = self.commit(
            "initial",
            {"README": "BlastEX\n", "scripts/deploy_vps.sh": DEPLOY_STUB},
        )
        self.git(tmp_path, "clone", "-q", str(self.origin), str(self.app))

    def git(self, cwd: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", *args], cwd=cwd, env=self.env, capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr
        return result.stdout.strip()

    def commit(self, message: str, files: dict[str, str] | None = None, branch: str = "main") -> str:
        """Коммит в ``seed`` и push в ``origin``; возвращает SHA."""
        if branch != "main":
            self.git(self.seed, "checkout", "-q", "-B", branch)
        for name, text in (files or {message.replace(" ", "_"): message}).items():
            path = self.seed / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            if name.endswith(".sh"):
                path.chmod(0o755)
        self.git(self.seed, "add", "-A")
        self.git(self.seed, "commit", "-q", "-m", message)
        sha = self.git(self.seed, "rev-parse", "HEAD")
        self.git(self.seed, "push", "-q", "origin", f"HEAD:refs/heads/{branch}")
        if branch != "main":
            self.git(self.seed, "checkout", "-q", "main")
        return sha

    def run(self, command: str, **extra_env: str) -> subprocess.CompletedProcess[str]:
        env = dict(
            self.env,
            SSH_ORIGINAL_COMMAND=command,
            APP_DIR=str(self.app),
            DEPLOY_LOCK_FILE=str(self.lock),
            STUB_LOG=str(self.log),
            **extra_env,
        )
        return subprocess.run(
            [str(SCRIPT)], env=env, capture_output=True, text=True, timeout=60
        )

    def deployed(self) -> list[str]:
        if not self.log.exists():
            return []
        return self.log.read_text(encoding="utf-8").split()

    def head(self) -> str:
        return self.git(self.app, "rev-parse", "HEAD")

    def marker(self) -> str | None:
        result = subprocess.run(
            ["git", "rev-parse", "-q", "--verify", DEPLOYED_REF],
            cwd=self.app,
            env=self.env,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() or None


@pytest.fixture
def stand(tmp_path: Path) -> Stand:
    return Stand(tmp_path)


def test_deploys_requested_commit(stand: Stand) -> None:
    sha = stand.commit("second")

    result = stand.run(sha)

    assert result.returncode == 0, result.stderr
    assert stand.deployed() == [sha]
    assert stand.head() == sha
    assert stand.marker() == sha


def test_deploys_tested_commit_when_main_moved_ahead(stand: Stand) -> None:
    # Прогон проверил tested; пока он шёл, в main попал коммит с падающим
    # тестом. На прод уходит проверенный, следующий выкатит свой прогон.
    tested = stand.commit("tested")
    stand.commit("untested")

    result = stand.run(tested)

    assert result.returncode == 0, result.stderr
    assert stand.deployed() == [tested]
    assert stand.head() == tested
    assert stand.marker() == tested


@pytest.mark.parametrize(
    "mangle",
    [
        lambda sha: "",
        lambda sha: sha[:39],
        lambda sha: sha + "0",
        lambda sha: sha.upper(),
        lambda sha: " " + sha,
        lambda sha: sha + " ",
        lambda sha: sha + "\n",
        lambda sha: sha + ";id",
        lambda sha: f"{sha} {sha}",
        lambda sha: "main",
    ],
    ids=["empty", "short", "long", "upper", "lead-space", "trail-space", "newline",
         "shell", "two-args", "ref-name"],
)
def test_rejects_malformed_command(stand: Stand, mangle) -> None:
    sha = stand.commit("second")
    command = mangle(sha)
    assert command != sha

    result = stand.run(command)

    assert result.returncode == REJECTED, result.stderr
    assert stand.deployed() == []
    assert stand.head() == stand.initial


def test_rejects_unknown_commit(stand: Stand) -> None:
    result = stand.run("0123456789abcdef" * 2 + "01234567")

    assert result.returncode == REJECTED, result.stderr
    assert stand.deployed() == []


def test_rejects_commit_outside_main(stand: Stand) -> None:
    # Коммит есть и в origin, и на сервере, но не в main — например, ручной
    # запуск workflow на ветке PR.
    sha = stand.commit("not merged", branch="feature")
    stand.git(stand.app, "fetch", "-q", "origin", "feature")

    result = stand.run(sha)

    assert result.returncode == REJECTED, result.stderr
    assert stand.deployed() == []
    assert stand.head() == stand.initial


def test_rejects_commit_older_than_deployed(stand: Stand) -> None:
    # Порядок прогонов в concurrency-группе не гарантирован, а перезапуск
    # старого прогона шлёт его SHA: без этой проверки прод откатился бы.
    older = stand.commit("older")
    newer = stand.commit("newer")
    assert stand.run(newer).returncode == 0

    result = stand.run(older)

    assert result.returncode == REJECTED, result.stderr
    assert stand.deployed() == [newer]
    assert stand.head() == newer
    assert stand.marker() == newer


def test_redeploys_deployed_commit(stand: Stand) -> None:
    # Ручной запуск на том же main пересобирает прод — например, после
    # правки .env.
    sha = stand.commit("second")
    assert stand.run(sha).returncode == 0

    result = stand.run(sha)

    assert result.returncode == 0, result.stderr
    assert stand.deployed() == [sha, sha]


def test_failed_deploy_keeps_previous_marker(stand: Stand) -> None:
    good = stand.commit("good")
    assert stand.run(good).returncode == 0
    broken = stand.commit("broken build")

    result = stand.run(broken, STUB_EXIT="3")

    assert result.returncode == 3
    assert stand.marker() == good
    # Повтор того же коммита после починки сервера его выкатывает.
    assert stand.run(broken).returncode == 0
    assert stand.marker() == broken


def test_fetch_failure_keeps_git_exit_code(stand: Stand) -> None:
    # На коде 128 workflow повторяет попытку: GitHub временно ограничивает
    # анонимные скачивания.
    stand.git(stand.app, "remote", "set-url", "origin", str(stand.tmp / "missing.git"))

    result = stand.run(stand.initial)

    assert result.returncode == 128, result.stderr
    assert stand.deployed() == []


def test_rejects_modified_tracked_files(stand: Stand) -> None:
    sha = stand.commit("second")
    readme = stand.app / "README"
    readme.write_text("hotfix on server\n", encoding="utf-8")

    result = stand.run(sha)

    assert result.returncode == REJECTED, result.stderr
    assert stand.deployed() == []
    assert readme.read_text(encoding="utf-8") == "hotfix on server\n"


def test_refuses_to_run_concurrently(stand: Stand) -> None:
    sha = stand.commit("second")
    fd = os.open(stand.lock, os.O_CREAT | os.O_WRONLY, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        result = stand.run(sha)
    finally:
        os.close(fd)

    assert result.returncode == BUSY, result.stderr
    assert stand.deployed() == []


def test_warns_when_installed_copy_is_stale(stand: Stand) -> None:
    sha = stand.commit("new forced command", {"scripts/deploy_forced_command.sh": "#!/bin/sh\n"})

    result = stand.run(sha)

    assert result.returncode == 0, result.stderr
    assert "WARNING" in result.stderr


def test_no_warning_when_installed_copy_matches(stand: Stand) -> None:
    sha = stand.commit(
        "same forced command",
        {"scripts/deploy_forced_command.sh": SCRIPT.read_text(encoding="utf-8")},
    )

    result = stand.run(sha)

    assert result.returncode == 0, result.stderr
    assert "WARNING" not in result.stderr


def _deploy_job() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["deploy"]


def _deploy_step() -> dict:
    return next(
        step for step in _deploy_job()["steps"] if step.get("name") == "Deploy to production VPS"
    )


def test_workflow_passes_tested_sha_through_env() -> None:
    step = _deploy_step()

    assert step["env"]["DEPLOY_SHA"] == "${{ github.sha }}"
    assert "${{" not in step["run"]


def test_workflow_deploys_only_from_main() -> None:
    condition = _deploy_job()["if"]

    assert "github.event_name != 'pull_request'" in condition
    assert "github.ref == 'refs/heads/main'" in condition


def _run_deploy_step(tmp_path: Path, codes: str) -> tuple[subprocess.CompletedProcess[str], list[list[str]]]:
    """Исполняет run шага деплоя с поддельным ssh, отвечающим кодами ``codes``."""
    step = _deploy_step()
    _write_executable(tmp_path / "bin" / "ssh", FAKE_SSH)
    calls = tmp_path / "ssh-calls.jsonl"
    env = {key: value for key, value in step["env"].items() if "${{" not in str(value)}
    env.update(
        PATH=f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}",
        HOME=str(tmp_path),
        DEPLOY_HOST="vps.example",
        DEPLOY_USER="deploy",
        DEPLOY_SHA="0123456789abcdef" * 2 + "01234567",
        DEPLOY_RETRY_DELAY_SECONDS="0",
        FAKE_SSH_CALLS=str(calls),
        FAKE_SSH_CODES=codes,
    )
    script = tmp_path / "step.sh"
    script.write_text(step["run"], encoding="utf-8")
    # Так GitHub Actions запускает `run` на ubuntu-latest по умолчанию.
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", str(script)],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    lines = calls.read_text(encoding="utf-8").splitlines() if calls.exists() else []
    return result, [json.loads(line) for line in lines]


def test_workflow_sends_sha_as_ssh_command_with_keepalive(tmp_path: Path) -> None:
    result, calls = _run_deploy_step(tmp_path, "0")

    assert result.returncode == 0, result.stdout + result.stderr
    assert len(calls) == 1
    args = calls[0]
    assert args[-2:] == ["deploy@vps.example", "0123456789abcdef" * 2 + "01234567"]
    assert "ServerAliveInterval=30" in args
    assert "ServerAliveCountMax=20" in args


def test_workflow_retries_fetch_failure(tmp_path: Path) -> None:
    result, calls = _run_deploy_step(tmp_path, "128 0")

    assert result.returncode == 0, result.stdout + result.stderr
    assert len(calls) == 2


def test_workflow_gives_up_after_attempts(tmp_path: Path) -> None:
    result, calls = _run_deploy_step(tmp_path, "128 128 128")

    assert result.returncode == 128
    assert len(calls) == 3


def test_workflow_does_not_retry_rejected_commit(tmp_path: Path) -> None:
    result, calls = _run_deploy_step(tmp_path, f"{REJECTED} 0")

    assert result.returncode == REJECTED
    assert len(calls) == 1
