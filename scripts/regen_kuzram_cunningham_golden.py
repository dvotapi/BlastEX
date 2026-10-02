"""Независимая реализация Kuz-Ram по Каннингему (EFEE 2005) для эталона подбора q.

Не импортирует код проекта: эталон tests/fixtures/kuzram_cunningham_golden.json
сверяет Blast.py::optimize_blast с этой реализацией, а не с самим собой.

    python scripts/regen_kuzram_cunningham_golden.py tests/fixtures/kuzram_cunningham_golden.json check
    python scripts/regen_kuzram_cunningham_golden.py tests/fixtures/kuzram_cunningham_golden.json write

check — пересчитать строки эталона и показать наибольшее отклонение;
write — переписать строки (q, ЛНС, x50, n, негабарит, A) по формулам ниже.
check-old — то же для прежней силы ВВ к тротилу, RE^−e (kuzram-cunningham-1.0).
"""
import json
import math
import sys


def rock_factor(s, ucs, rho, ff, W, S):
    corr = s["rock_factor_correction"]
    if s["rock_factor_method"] == "manual":
        return s["rock_factor_manual"] * corr
    rdi = 25 * rho - 50
    hf = ucs / 5
    if s["rock_factor_method"] == "rmd10":
        rmd = 10.0
    elif s["rock_factor_method"] == "joint_factor" and ff > 0:
        spacing = 1 / ff
        p = math.sqrt(W * S)
        jps = 10.0 if spacing < 0.1 else 20.0 if spacing < 0.3 else 80.0 if spacing < 0.95 * p else 50.0
        rmd = s["joint_condition"] * jps + s["joint_angle"]
    else:
        rmd = 50.0
    return 0.06 * (rmd + rdi + hf) * corr


def point(case, crown, q, mode):
    r, e, t, s = case["rock"], case["explosive"], case["target"], case["settings"]
    d_m = crown / 1000 * t["hole_oversize_coeff"]
    depth = t["bench_height_m"] + t["overdrill_m"]
    L = depth * 0.8
    Q = math.pi * d_m ** 2 / 4 * e["density_t_m3"] * 1000 * depth * 0.8
    V = Q / q
    W = math.sqrt(V / (t["spacing_coeff_m"] * t["bench_height_m"]))
    m = t["spacing_coeff_m"]
    A = rock_factor(s, r["ucs_mpa"], r["density_t_m3"], r["fissuring_ff"], W, m * W)
    ex = 19 / 20 if s["strength_exponent"] == "19/20" else 19 / 30
    if mode == "old":
        strength = (e["power_mj_kg"] / 4.184) ** (-ex)
    else:
        strength = (115 / (100 * e["power_mj_kg"] / 3.8)) ** ex
    x50 = A * q ** -0.8 * Q ** (1 / 6) * strength * 10
    lh = min(1.0, L / t["bench_height_m"])
    n = (
        (2.2 - 14 * W / (d_m * 1000))
        * math.sqrt((1 + m) / 2)
        * max(0.0, 1 - s["drill_deviation_m"] / W)
        * 1.1 ** 0.1
        * lh
        * s["uniformity_correction"]
    )
    n = max(0.1, n)
    xc = x50 / math.log(2) ** (1 / n)
    over = math.exp(-((t["lump_size_mm"] / xc) ** n)) * 100
    return dict(burden_m=W, x50_mm=x50, n=n, oversize_pct=over, rock_factor_a=A)


def optimize(case, crown, mode):
    last = math.floor(case["settings"]["q_max_kg_m3"] * 100 + 1e-9)
    for i in range(10, last + 1):
        p = point(case, crown, i / 100, mode)
        if p["oversize_pct"] <= case["threshold"]:
            return i / 100, p, True
    return last / 100, point(case, crown, last / 100, mode), False


def main():
    path, action = sys.argv[1], sys.argv[2]
    data = json.load(open(path, encoding="utf-8"))
    worst = 0.0
    for case in data["cases"]:
        for row in case["rows"]:
            mode = "old" if action == "check-old" else "new"
            q, p, reached = optimize(case, row["crown_mm"], mode)
            if action in ("check", "check-old"):
                assert q == row["q"] and reached == row["reached"], (row, q, reached)
                for k, v in p.items():
                    worst = max(worst, abs(v - row[k]) / max(abs(row[k]), 1e-12))
            else:
                row.update(q=q, reached=reached, **p)
    if action in ("check", "check-old"):
        print("max rel diff vs fixture:", worst)
    else:
        data["source"] = (
            "Независимая реализация Kuz-Ram по Каннингему (EFEE 2005), сила ВВ — (115/RWS)^e, "
            "RWS = 100·Q/3,8 к ANFO; seed 20260922"
        )
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
            fh.write("\n")
        print("written")


main()
