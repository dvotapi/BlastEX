"""Независимая проверка файлов LibreOffice: файл открывает не та библиотека, что его писала."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


def convert(source: Path, target: str, workdir: Path) -> Path:
    """`soffice --headless --convert-to target`; без LibreOffice — тест пропускается."""

    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice is None:
        pytest.skip("Нет LibreOffice (soffice)")
    profile = workdir / "lo-profile"
    subprocess.run(
        [soffice, f"-env:UserInstallation={profile.as_uri()}", "--headless", "--convert-to", target,
         str(source), "--outdir", str(workdir)],
        check=True, capture_output=True, timeout=180,
    )
    result = workdir / f"{source.stem}.{target.split(':')[0]}"
    assert result.exists(), f"LibreOffice не сконвертировал {source.name}"
    return result
