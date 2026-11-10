"""Конвертация DWG в DXF внешним конвертером.

DWG — закрытый бинарный формат Autodesk, читать его на Python нечем. Берём
`dwg2dxf` из GNU LibreDWG: он ставится в образ из исходников (см. Dockerfile),
работает как обычная утилита командной строки и, в отличие от ODA File
Converter, разрешён к коммерческому использованию.

Путь к конвертеру можно переопределить переменной `BLASTEX_DWG_CONVERTER` —
тогда подойдёт любая утилита с совместимыми аргументами
(`-y -m -o out.dxf in.dwg`).

Обратное направление — `dxf2dwg` из того же LibreDWG (TASK-015, PR 4): чертёж
скважин паспорта на бурение в DWG R2000 (`dxf_to_dwg`, переменная
`BLASTEX_DXF2DWG`, аргументы `-y --as r2000 -o out.dwg in.dxf`). LibreDWG
стабильно пишет только R2000 и старше.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

__all__ = ["DwgConversionError", "find_converter", "find_writer", "dwg_to_dxf", "dxf_to_dwg"]

CONVERTER_TIMEOUT_S = 120
# По умолчанию просим полный DXF: только в нём есть $INSUNITS и таблица слоёв
# с цветами. На части чертежей полный вывод LibreDWG содержит нулевые и
# повторяющиеся дескрипторы объектов, на которых ezdxf падает («Invalid handle
# 0») даже в режиме восстановления. Тогда вызывающий повторяет конвертацию с
# `-m` — минимальным DXF (только $ACADVER, HANDSEED и ENTITIES): он читается
# штатно, слои, отметки и координаты примитивов в нём сохраняются полностью.
CONVERTER_ARGS = ("-y",)
MINIMAL_ARG = "-m"
WRITER_ARGS = ("-y", "--as", "r2000")
NO_CONVERTER_MESSAGE = (
    "На сервере не установлен конвертер DWG. "
    "Сохраните чертёж как DXF (Файл → Сохранить как → AutoCAD DXF) и загрузите его."
)


class DwgConversionError(Exception):
    """DWG не удалось привести к DXF."""


def _find_tool(variable: str, name: str) -> str | None:
    """Путь к утилите: из переменной окружения (если файл есть) или из PATH."""

    configured = os.getenv(variable, "").strip()
    if configured:
        return configured if Path(configured).exists() else None
    return shutil.which(name)


def find_converter() -> str | None:
    """Путь к dwg2dxf или None, если конвертер не установлен."""

    return _find_tool("BLASTEX_DWG_CONVERTER", "dwg2dxf")


def find_writer() -> str | None:
    """Путь к dxf2dwg или None, если утилита не установлена."""

    return _find_tool("BLASTEX_DXF2DWG", "dxf2dwg")


@dataclass(frozen=True)
class _Tool:
    """Тексты ошибок утилиты для пользователя."""

    name: str  # «Конвертер DWG не запускается»
    timeout: str
    failure: str  # первая фраза при пустом результате
    detail: str  # «Конвертер сообщил»
    empty_hint: str = ""


CONVERTER = _Tool(
    "Конвертер DWG",
    "Конвертер DWG не ответил за отведённое время.",
    "Не удалось прочитать DWG.",
    "Конвертер сообщил",
    " Проверьте, что файл не повреждён.",
)
WRITER = _Tool(
    "Утилита записи DWG",
    "Утилита записи DWG не ответила за отведённое время.",
    "Не удалось записать DWG.",
    "Утилита сообщила",
)


def _run_tool(path: str, args: Sequence[str], data: bytes, source_name: str, target_suffix: str, tool: _Tool) -> bytes:
    """Запускает утилиту LibreDWG над временным файлом и возвращает результат.

    Ошибка запуска, таймаут или пустой результат — `DwgConversionError`.
    Проверяется файл, а не код возврата: утилита может завершиться успешно и
    не создать его.
    """

    with tempfile.TemporaryDirectory(prefix="blastex-dwg-") as work:
        source = Path(work) / source_name
        target = source.with_suffix(target_suffix)
        source.write_bytes(data)
        try:
            completed = subprocess.run(  # noqa: S603 — путь берётся из конфигурации сервера
                [path, *args, "-o", str(target), str(source)],
                capture_output=True,
                timeout=CONVERTER_TIMEOUT_S,
                check=False,
            )
        except FileNotFoundError as exc:
            raise DwgConversionError(f"{tool.name} не запускается: {path}.") from exc
        except subprocess.TimeoutExpired as exc:
            raise DwgConversionError(tool.timeout) from exc
        if not target.exists() or not target.stat().st_size:
            detail = (completed.stderr or completed.stdout or b"").decode("utf-8", "replace").strip()
            raise DwgConversionError(
                tool.failure + (f" {tool.detail}: {detail[-300:]}" if detail else tool.empty_hint)
            )
        return target.read_bytes()


def dxf_to_dwg(data: bytes) -> bytes:
    """Конвертирует байты DXF в DWG R2000; ошибка — `DwgConversionError`."""

    writer = find_writer()
    if not writer:
        raise DwgConversionError("На сервере не установлена утилита записи DWG (dxf2dwg).")
    return _run_tool(writer, WRITER_ARGS, data, "drawing.dxf", ".dwg", WRITER)


def dwg_to_dxf(data: bytes, filename: str = "drawing.dwg", *, minimal: bool = False) -> bytes:
    """Конвертирует байты DWG в байты DXF (минимальный DXF — по запросу)."""

    converter = find_converter()
    if not converter:
        raise DwgConversionError(NO_CONVERTER_MESSAGE)
    safe_name = Path(filename).name or "drawing.dwg"
    if not safe_name.lower().endswith(".dwg"):
        safe_name = f"{safe_name}.dwg"
    args = (*CONVERTER_ARGS, *((MINIMAL_ARG,) if minimal else ()))
    return _run_tool(converter, args, data, safe_name, ".dxf", CONVERTER)
