"""Единые правила «прогноз кусковатости посчитан старой базой Kuz-Ram 1.0.0».

Все калибровки кусковатости обучены на этой базе, а негабарит — ещё и на кривой
Kuz-Ram. Правила зовут и сервер `/calibration/predict` (присланный baseline), и
обучение (строки снимка), чтобы они не расходились.
"""
from __future__ import annotations

import re

from simulation.fragmentation.engine import resolve_model
from simulation.fragmentation.models import LEGACY_MODEL_SUFFIX, MODEL_KUZRAM, MODEL_KUZRAM_LEGACY

# Версий длиннее шести цифр не бывает; ограничение защищает `int()`, который на
# очень длинной строке цифр бросает ValueError.
_MAJOR = re.compile(r"[0-9]{1,6}")


def version_major(version: str) -> int | None:
    """Номер основной версии («1.0.0» → 1); None — версия не распознана."""
    major = str(version or "").strip().split(".")[0]
    return int(major) if _MAJOR.fullmatch(major) else None


def is_old_base(model: str, version: str) -> bool:
    """Прогноз посчитан старой базой: модель не записана, `*_legacy` или версия ниже 2.

    Пустая модель — прогноз, сохранённый до того, как снимок стал хранить модель:
    тогда считала старая база. Нераспознанная версия у не-legacy модели — не
    старая база: чужую формулу лучше не взять, чем взять.
    """
    model = str(model or "").strip().lower()
    if not model or model.endswith(LEGACY_MODEL_SUFFIX):
        return True
    major = version_major(version)
    return major is not None and major < 2


def is_kuzram_curve(model: str) -> bool:
    """Модель считает негабарит по кривой Kuz-Ram (`kuzram` или `kuzram_legacy`).

    x50 старых моделей совпадает, а негабарит у них разный (другое распределение),
    поэтому калибровка негабарита, обученная на кривой Kuz-Ram, ложится только на неё.
    Пустое и неизвестное имя — не Kuz-Ram.
    """
    if not str(model or "").strip():
        return False
    try:
        return resolve_model(model) in {MODEL_KUZRAM, MODEL_KUZRAM_LEGACY}
    except ValueError:
        return False
