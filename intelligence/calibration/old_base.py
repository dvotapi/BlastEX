"""Единое правило «прогноз кусковатости посчитан старой базой Kuz-Ram 1.0.0».

Все калибровки кусковатости обучены на этой базе. Правило зовут и сервер
`/calibration/predict` (присланный baseline), и обучение (строки снимка), чтобы
они не расходились.
"""
from __future__ import annotations

import re

from simulation.fragmentation.models import LEGACY_MODEL_SUFFIX

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
