"""Файл выноса скважин для GNSS-приёмника (TASK-015, PR 5, спека §5)."""
from __future__ import annotations

from design.export_survey import BUILTIN_PROFILES, DEFAULT_STAKEOUT_PROFILE, stakeout_snapshot


def test_stakeout_snapshot_builtin_profiles() -> None:
    snapshot = stakeout_snapshot({}, None)
    assert DEFAULT_STAKEOUT_PROFILE == "PNEZD_CSV"
    assert snapshot["default"] == "PNEZD_CSV"
    assert list(snapshot["profiles"]) == ["PNEZD_CSV", "PENZD_CSV", "PNEZ_TXT", "DXF_POINTS"]
    assert snapshot["profiles"] == BUILTIN_PROFILES
    assert snapshot["profiles"]["PENZD_CSV"] == {
        "name": "PENZD_CSV", "format": "PENZD_CSV", "header": False, "elevation": True, "include_toe": False,
    }


def test_stakeout_snapshot_reference_records() -> None:
    records = {
        "TRIMBLE": {"name": "Trimble Access", "format": "PENZD_CSV", "header": True},
        "PNEZD_CSV": {"name": "Без отметок", "format": "PNEZD_CSV", "elevation": False},
    }
    snapshot = stakeout_snapshot(records, "TRIMBLE")
    assert snapshot["default"] == "TRIMBLE"
    assert snapshot["profiles"]["TRIMBLE"] == {
        "name": "Trimble Access", "format": "PENZD_CSV", "header": True, "elevation": True, "include_toe": False,
    }
    # Запись с кодом встроенного профиля его заменяет.
    assert snapshot["profiles"]["PNEZD_CSV"]["elevation"] is False
    assert len(snapshot["profiles"]) == 5


def test_stakeout_snapshot_unknown_default_falls_back() -> None:
    assert stakeout_snapshot({}, "NOPE")["default"] == "PNEZD_CSV"
