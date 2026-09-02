"""Конвертация DWG в DXF внешним конвертером.

DWG — закрытый бинарный формат Autodesk, читать его на Python нечем. Берём
`dwg2dxf` из GNU LibreDWG: он ставится в образ из исходников (см. Dockerfile),
работает как обычная утилита командной строки и, в отличие от ODA File
Converter, разрешён к коммерческому использованию.

Путь к конвертеру можно переопределить переменной `BLASTEX_DWG_CONVERTER` —
тогда подойдёт любая утилита с совместимыми аргументами (`-y -o out.dxf in.dwg`).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

__all__ = ["DwgConversionError", "find_converter", "dwg_to_dxf"]

CONVERTER_TIMEOUT_S = 120
NO_CONVERTER_MESSAGE = (
    "На сервере не установлен конвертер DWG. "
    "Сохраните чертёж как DXF (Файл → Сохранить как → AutoCAD DXF) и загрузите его."
)


class DwgConversionError(Exception):
    """DWG не удалось привести к DXF."""


def find_converter() -> str | None:
    """Путь к dwg2dxf или None, если конвертер не установлен."""

    configured = os.getenv("BLASTEX_DWG_CONVERTER", "").strip()
    if configured:
        return configured if Path(configured).exists() else None
    return shutil.which("dwg2dxf")


def dwg_to_dxf(data: bytes, filename: str = "drawing.dwg") -> bytes:
    """Конвертирует байты DWG в байты DXF."""

    converter = find_converter()
    if not converter:
        raise DwgConversionError(NO_CONVERTER_MESSAGE)

    safe_name = Path(filename).name or "drawing.dwg"
    if not safe_name.lower().endswith(".dwg"):
        safe_name = f"{safe_name}.dwg"

    with tempfile.TemporaryDirectory(prefix="blastex-dwg-") as work:
        source = Path(work) / safe_name
        target = source.with_suffix(".dxf")
        source.write_bytes(data)

        try:
            completed = subprocess.run(  # noqa: S603 — путь берётся из конфигурации сервера
                [converter, "-y", "-o", str(target), str(source)],
                capture_output=True,
                timeout=CONVERTER_TIMEOUT_S,
                check=False,
            )
        except FileNotFoundError as exc:
            raise DwgConversionError(f"Конвертер DWG не запускается: {converter}.") from exc
        except subprocess.TimeoutExpired as exc:
            raise DwgConversionError("Конвертер DWG не ответил за отведённое время.") from exc

        # Конвертер может вернуть 0 и при этом не создать файл на битом чертеже,
        # поэтому проверяем результат, а не только код возврата.
        if not target.exists() or not target.stat().st_size:
            detail = (completed.stderr or completed.stdout or b"").decode("utf-8", "replace").strip()
            raise DwgConversionError(
                "Не удалось прочитать DWG."
                + (f" Конвертер сообщил: {detail[-300:]}" if detail else " Проверьте, что файл не повреждён.")
            )
        return target.read_bytes()
