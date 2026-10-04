"""График кривой машиниста (TASK-010) для `Docs/specs/payroll/`.

Строится теми же функциями, что считают премию (`cost.model.payroll`), — картинка
не расходится с моделью. Запуск из корня репозитория:

    .venv/bin/python scripts/plot_payroll_curve.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from cost.model.payroll import Scale, scale_series  # noqa: E402
from cost.v2.payroll_defaults import DRILLER_SCALE  # noqa: E402
from decimal import Decimal  # noqa: E402

OUTPUT = ROOT / "Docs" / "specs" / "payroll" / "Шкала машиниста — степенная кривая.png"


def main() -> None:
    scale = Scale(
        DRILLER_SCALE["scale_type"],
        norm_per_shift=Decimal(DRILLER_SCALE["norm_per_shift"]),
        rate_norm=Decimal(DRILLER_SCALE["rate_norm"]),
        ceiling_per_shift=Decimal(DRILLER_SCALE["ceiling_per_shift"]),
        rate_ceiling=Decimal(DRILLER_SCALE["rate_ceiling"]),
    )
    points = scale_series(scale)
    paces = [float(point.pace) for point in points]
    figure, (rate_axis, premium_axis) = plt.subplots(1, 2, figsize=(11, 4.2), dpi=150)
    rate_axis.plot(paces, [float(point.rate) for point in points], color="#1f5fa8", linewidth=2)
    rate_axis.set_title("Цена приведённого метра r(m), ₽")
    premium_axis.plot(paces, [float(point.per_shift) for point in points], color="#b5562a", linewidth=2)
    premium_axis.set_title("Премия за смену p(m), ₽")
    for axis in (rate_axis, premium_axis):
        for node, label in ((scale.norm_per_shift, "норма"), (scale.ceiling_per_shift, "потолок")):
            axis.axvline(float(node), color="#888888", linestyle="--", linewidth=1)
            axis.annotate(f"{label} {float(node):.1f}", (float(node), axis.get_ylim()[1]), rotation=90,
                          va="top", ha="right", fontsize=8, color="#555555")
        axis.set_xlabel("приведённых м за эффективную смену")
        axis.grid(alpha=0.3)
    figure.suptitle(f"Кривая машиниста: 45 ₽ на норме, 168,66 ₽ на потолке, γ = {format(float(scale.gamma), '.3f').replace('.', ',')}")
    figure.tight_layout()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(OUTPUT)
    print(OUTPUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
