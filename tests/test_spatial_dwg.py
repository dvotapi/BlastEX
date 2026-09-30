"""Вызов внешнего конвертера DWG → DXF."""
from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from design.spatial import dwg


# Разбор аргументов dwg2dxf: `-o <выход>` и последний аргумент — входной DWG.
# Позиции зависят от флага `-m`, поэтому скрипт ищет их, а не берёт $4/$5.
_ARGS_PRELUDE = (
    'OUT=""; IN=""\n'
    'while [ $# -gt 0 ]; do\n'
    '  if [ "$1" = "-o" ]; then OUT="$2"; shift; fi\n'
    '  IN="$1"; shift\n'
    'done\n'
)


def _fake_converter(tmp_path: Path, body: str) -> str:
    """Пишет исполняемый скрипт, изображающий dwg2dxf."""

    script = tmp_path / "fake-dwg2dxf"
    script.write_text("#!/bin/sh\n" + _ARGS_PRELUDE + body)
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


def test_converter_is_taken_from_the_environment(tmp_path, monkeypatch):
    path = _fake_converter(tmp_path, "exit 0\n")
    monkeypatch.setenv("BLASTEX_DWG_CONVERTER", path)
    assert dwg.find_converter() == path


def test_missing_configured_converter_is_reported_as_absent(monkeypatch):
    monkeypatch.setenv("BLASTEX_DWG_CONVERTER", "/nowhere/dwg2dxf")
    assert dwg.find_converter() is None


def test_conversion_returns_the_produced_dxf(tmp_path, monkeypatch):
    path = _fake_converter(tmp_path, 'printf "DXF PAYLOAD" > "$OUT"\nexit 0\n')
    monkeypatch.setenv("BLASTEX_DWG_CONVERTER", path)
    assert dwg.dwg_to_dxf(b"AC1032", "block.dwg") == b"DXF PAYLOAD"


def test_conversion_passes_the_source_bytes(tmp_path, monkeypatch):
    path = _fake_converter(tmp_path, 'cat "$IN" > "$OUT"\nexit 0\n')
    monkeypatch.setenv("BLASTEX_DWG_CONVERTER", path)
    assert dwg.dwg_to_dxf(b"original bytes", "block.dwg") == b"original bytes"


def test_silent_failure_is_reported_with_the_converter_output(tmp_path, monkeypatch):
    # Конвертер может завершиться успешно и не создать файл — это тоже ошибка.
    path = _fake_converter(tmp_path, 'echo "unsupported version" >&2\nexit 0\n')
    monkeypatch.setenv("BLASTEX_DWG_CONVERTER", path)
    with pytest.raises(dwg.DwgConversionError) as exc:
        dwg.dwg_to_dxf(b"AC1032", "block.dwg")
    assert "unsupported version" in str(exc.value)


def test_without_a_converter_the_user_is_told_to_save_as_dxf(monkeypatch):
    monkeypatch.delenv("BLASTEX_DWG_CONVERTER", raising=False)
    monkeypatch.setattr(dwg.shutil, "which", lambda name: None)
    with pytest.raises(dwg.DwgConversionError) as exc:
        dwg.dwg_to_dxf(b"AC1032", "block.dwg")
    assert "DXF" in str(exc.value)


def test_temporary_files_are_cleaned_up(tmp_path, monkeypatch):
    path = _fake_converter(tmp_path, 'printf "DXF" > "$OUT"\nexit 0\n')
    monkeypatch.setenv("BLASTEX_DWG_CONVERTER", path)
    before = set(os.listdir(tmp_path.parent))
    dwg.dwg_to_dxf(b"AC1032", "block.dwg")
    leftovers = [name for name in set(os.listdir(tmp_path.parent)) - before if name.startswith("blastex-dwg-")]
    assert leftovers == []


def _recorded_args(tmp_path: Path, monkeypatch, **kwargs) -> list[str]:
    recorded = tmp_path / "args.txt"
    script = tmp_path / "record-dwg2dxf"
    script.write_text(
        "#!/bin/sh\n"
        f'printf "%s" "$*" > "{recorded}"\n'
        + _ARGS_PRELUDE
        + 'printf "DXF" > "$OUT"\nexit 0\n'
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("BLASTEX_DWG_CONVERTER", str(script))
    dwg.dwg_to_dxf(b"AC1032", "block.dwg", **kwargs)
    return recorded.read_text().split()


def test_full_dxf_is_requested_by_default(tmp_path, monkeypatch):
    """Полный DXF несёт $INSUNITS и таблицу слоёв с цветами."""

    args = _recorded_args(tmp_path, monkeypatch)
    assert args[:2] == ["-y", "-o"]
    assert "-m" not in args


def test_minimal_dxf_is_requested_on_demand(tmp_path, monkeypatch):
    """Минимальный DXF — запасной путь, когда ezdxf не читает полный."""

    args = _recorded_args(tmp_path, monkeypatch, minimal=True)
    assert args[:3] == ["-y", "-m", "-o"]
