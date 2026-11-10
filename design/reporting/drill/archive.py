"""Zip с постоянными байтами: XLSX ведомости и архив документов ревизии (TASK-015, PR 5).

`zipfile` ставит записям текущее время; повторный выпуск ревизии должен дать
те же байты, поэтому время записей — постоянное (1980-01-01, наименьшее в zip).
"""
from __future__ import annotations

import io
import zipfile
from collections.abc import Iterable

__all__ = ["FIXED_ZIP_TIME", "build_zip", "fixed_zip"]

FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def build_zip(entries: Iterable[tuple[str, bytes]]) -> bytes:
    """Zip из записей в заданном порядке, сжатие deflate, время записей постоянное."""

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries:
            info = zipfile.ZipInfo(name, date_time=FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)
    return output.getvalue()


def fixed_zip(data: bytes) -> bytes:
    """Тот же zip (те же записи, тот же порядок) с постоянным временем записей."""

    with zipfile.ZipFile(io.BytesIO(data)) as source:
        return build_zip((info.filename, source.read(info)) for info in source.infolist())
