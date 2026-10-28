"""Чувствительность `PIECE_RATE` в режиме методики ФОТ (TASK-010 PR 3b).

Фактор «Сдельные расценки» двигает не только `piece_rate_rub`, но и шкалы
методики: расценку на норме и на потолке и ставки ступеней (пороги — нет).
"""
from __future__ import annotations

from decimal import Decimal

from cost.model import sensitivity
from cost.model.engine import compute_block_economics
from tests import model_fixtures as fx
from tests import test_model_block_payroll as bp

D = Decimal


def _row(rows, code: str):
    return next(row for row in rows if row.code == code)


def _variable_total(economics) -> Decimal:
    return sum((D(str(p["variable_rub"])) for p in economics.payroll["positions"]), D("0"))


def _price(references, params, physical=None) -> Decimal:
    snapshot = {"physical": physical or fx.physical(), "lineage": {}}
    return compute_block_economics(snapshot, params, references, as_of=bp.AS_OF).price_per_m3["full"]


def test_piece_rate_moves_payroll_crew() -> None:
    """Эффект строки = прежний (расценки прочих должностей) + 10 % переменной части экипажа методики."""

    references = bp._references()
    params = fx.parameters(crew=bp.CREW, payroll_source="PAYROLL")
    base = compute_block_economics(fx.snapshot(), params, references, as_of=bp.AS_OF)
    crew_effect = D("0.1") * _variable_total(base) / base.block_volume_m3
    legacy = sensitivity._scale_reference("labor_rates", "piece_rate_rub")
    for factor, sign in ((D("1.1"), 1), (D("0.9"), -1)):
        _, _, only_rates = legacy((fx.physical(), params, references), factor)
        legacy_effect = _price(only_rates, params) - base.price_per_m3["full"]
        expected = legacy_effect + sign * crew_effect
        actual = _price(sensitivity._scale_piece_rates((fx.physical(), params, references), factor)[2], params)
        assert crew_effect > 0
        assert abs((actual - base.price_per_m3["full"]) - expected) <= crew_effect * D("0.01")

    row = _row(sensitivity.compute(fx.snapshot(), params, references, as_of=bp.AS_OF), "PIECE_RATE")
    assert row.base_price == base.price_per_m3["full"]
    assert row.price_plus - row.base_price > crew_effect
    assert row.base_price - row.price_minus > crew_effect


def test_piece_rate_in_rates_mode_unchanged() -> None:
    rows = {row.code: row for row in sensitivity.compute(fx.snapshot(), fx.parameters(), fx.references())}
    row = rows["PIECE_RATE"]
    references = fx.references()
    old = sensitivity._scale_reference("labor_rates", "piece_rate_rub")
    for factor, price in ((D("0.9"), row.price_minus), (D("1.1"), row.price_plus)):
        physical, params, changed = old((fx.physical(), fx.parameters(), references), factor)
        expected = compute_block_economics(
            {"physical": physical, "lineage": {}}, params, changed
        ).price_per_m3["full"]
        assert price == expected


def test_piece_rate_scales_tier_rates() -> None:
    tiers = [{"upto_per_shift": "100", "rate": "40"}, {"upto_per_shift": None, "rate": "60"}]
    rate = fx.item(
        "LR_T",
        "Ступени",
        {"position_code": "P_X", "scale_type": "TIERS", "tiers": tiers, "rate_norm": "45", "rate_ceiling": "170", "piece_rate_rub": "10"},
    )
    references = fx.references(labor_rates=(rate,))

    _, _, changed = sensitivity._scale_piece_rates((fx.physical(), fx.parameters(), references), D("1.1"))
    payload = changed.sections["labor_rates"][0].payload

    assert [D(str(t["rate"])) for t in payload["tiers"]] == [D("44.0"), D("66.0")]
    assert [t["upto_per_shift"] for t in payload["tiers"]] == ["100", None]
    assert D(str(payload["rate_norm"])) == D("49.5")
    assert D(str(payload["rate_ceiling"])) == D("187.0")
    assert D(str(payload["piece_rate_rub"])) == D("11.0")
    assert rate.payload["tiers"] == tiers and tiers[0]["rate"] == "40"


def test_piece_rate_skips_bad_values() -> None:
    """Нечисловые расценки и не-списочные `tiers` пропускаются без исключения."""

    rate = fx.item(
        "LR_BAD",
        "Мусор",
        {"position_code": "P_X", "tiers": "oops", "rate_norm": "abc", "rate_ceiling": "170"},
    )
    tiered = fx.item(
        "LR_TIERS",
        "Ступени",
        {"position_code": "P_Y", "tiers": [{"rate": "x"}, {"rate": "60"}, "bad", None]},
    )
    references = fx.references(labor_rates=(rate, tiered))

    _, _, changed = sensitivity._scale_piece_rates((fx.physical(), fx.parameters(), references), D("1.1"))
    first, second = (item.payload for item in changed.sections["labor_rates"])

    assert first["tiers"] == "oops" and first["rate_norm"] == "abc"
    assert D(str(first["rate_ceiling"])) == D("187.0")
    assert second["tiers"][0] == {"rate": "x"}
    assert D(str(second["tiers"][1]["rate"])) == D("66.0")
    assert second["tiers"][2:] == ["bad", None]
