"""Streamlit удалён: интерфейс — только React.

Тест держит границу: ни импортов, ни зависимости в списке пакетов. Иначе
резервный интерфейс вернётся по частям вместе с `st.session_state` в
расчётных модулях.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGES = ("api", "cost", "design", "simulation", "intelligence", "scripts")


def _python_files() -> list[Path]:
    files = [path for package in PACKAGES for path in (ROOT / package).rglob("*.py")]
    files.extend(ROOT.glob("*.py"))
    return [path for path in files if "__pycache__" not in path.parts]


def test_no_module_imports_streamlit() -> None:
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in _python_files()
        if "import streamlit" in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


def test_requirements_do_not_pull_streamlit() -> None:
    lines = [
        line.strip().lower()
        for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    for package in ("streamlit", "altair", "pydeck", "watchdog", "gitpython"):
        assert not [line for line in lines if line.startswith(package)], (
            f"{package} снова в зависимостях"
        )


def test_streamlit_entrypoints_are_gone() -> None:
    for path in ("app.py", "Streamlit", "cost/references_ui.py", "cost/admin_auth.py"):
        assert not (ROOT / path).exists(), f"{path} должен быть удалён"
