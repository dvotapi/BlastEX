"""
BlastEX — веб-интерфейс расчёта параметров взрывания (Streamlit).
"""
import streamlit as st
import pandas as pd

from Blast import (
    RockProperties,
    ExplosiveProperties,
    TargetParams,
    BlastEngine,
)

# --- Справочники ВВ и пород ---

EXPLOSIVES = {
    "Эмульсия (2.99 МДж/кг)": ExplosiveProperties("Эмульсия", 1.12, 2.99),
    "АНФО (типовой)": ExplosiveProperties("АНФО", 0.85, 3.76),
    "Граммонит 79/21": ExplosiveProperties("Граммонит 79/21", 0.95, 3.50),
    "ТНТ (эталон)": ExplosiveProperties("ТНТ", 1.0, 4.184),
}

ROCKS = {
    "Габбро-диабаз": RockProperties("Габбро-диабаз", 2.9, 168, 2.2),
    "Гранит": RockProperties("Гранит", 2.65, 150, 2.0),
    "Известняк": RockProperties("Известняк", 2.5, 80, 1.5),
    "Песчаник": RockProperties("Песчаник", 2.4, 100, 1.8),
}

CROWNS_MM = [130, 140, 152, 165]


def main():
    st.set_page_config(page_title="BlastEX", page_icon="💥", layout="wide")
    st.title("💥 BlastEX — расчёт параметров взрывания")
    st.caption("Выбор ВВ, породы и целевых параметров. Оптимизация удельного расхода по порогу негабарита.")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.subheader("Взрывчатое вещество (ВВ)")
        explosive_key = st.selectbox(
            "ВВ",
            options=list(EXPLOSIVES.keys()),
            index=0,
            key="explosive",
        )
        explosive = EXPLOSIVES[explosive_key]
        with st.expander("Параметры выбранного ВВ"):
            st.write(f"**{explosive.name}**")
            st.write(f"- Плотность заряжания: {explosive.density_t_m3} т/м³")
            st.write(f"- Теплота взрыва: {explosive.power_mj_kg} МДж/кг")

    with col2:
        st.subheader("Порода")
        rock_key = st.selectbox(
            "Порода",
            options=list(ROCKS.keys()),
            index=0,
            key="rock",
        )
        rock = ROCKS[rock_key]
        with st.expander("Параметры выбранной породы"):
            st.write(f"**{rock.name}**")
            st.write(f"- Плотность: {rock.density_t_m3} т/м³")
            st.write(f"- Предел прочности на сжатие: {rock.ucs_mpa} МПа")
            st.write(f"- Трещиноватость: {rock.fissuring_ff}")

    with col3:
        st.subheader("Целевые параметры (TargetParams)")
        with st.expander("Настройки цели", expanded=True):
            lump_size_mm = st.number_input(
                "Кондиционный размер куска (негабарит), мм",
                min_value=100,
                max_value=1200,
                value=400,
                step=50,
            )
            bench_height_m = st.number_input(
                "Высота уступа, м",
                min_value=5.0,
                max_value=25.0,
                value=10.0,
                step=0.5,
            )
            overdrill_m = st.number_input(
                "Перебур, м",
                min_value=0.0,
                max_value=3.0,
                value=1.0,
                step=0.1,
            )
            hole_oversize_coeff = st.number_input(
                "Коэффициент разбуривания",
                min_value=1.0,
                max_value=1.15,
                value=1.05,
                step=0.01,
            )
            spacing_coeff_m = st.number_input(
                "Коэффициент сетки (a/W)",
                min_value=1.0,
                max_value=2.0,
                value=1.25,
                step=0.05,
            )
        target = TargetParams(
            lump_size_mm=lump_size_mm,
            hole_diameter_mm=0,
            overdrill_m=overdrill_m,
            hole_oversize_coeff=hole_oversize_coeff,
            spacing_coeff_m=spacing_coeff_m,
            bench_height_m=bench_height_m,
        )

    st.divider()

    max_oversize = st.slider(
        "Порог негабарита, % (целевой максимум)",
        min_value=1.0,
        max_value=15.0,
        value=5.0,
        step=0.5,
    )
    crowns = st.multiselect(
        "Диаметры коронок, мм",
        options=CROWNS_MM,
        default=CROWNS_MM,
    )

    if st.button("Рассчитать", type="primary"):
        if not crowns:
            st.warning("Выберите хотя бы один диаметр коронки.")
        else:
            engine = BlastEngine(rock, explosive, target)
            rows = []
            for d in sorted(crowns):
                res = engine.optimize_blast(d, max_oversize_threshold=max_oversize)
                a_m = round(target.spacing_coeff_m * res["W_m"], 2)
                b_m = res["W_m"]
                rows.append({
                    "Коронка (мм)": d,
                    "Уд. расход (кг/м³)": res["q"],
                    "ЛНС W (м)": res["W_m"],
                    "Сетка a×b (м)": f"{a_m} × {b_m}",
                    "x50 (мм)": res["x50_mm"],
                    "Негабарит (%)": res["oversize_pct"],
                })
            df = pd.DataFrame(rows)
            st.subheader("Результаты оптимизации")
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.caption(f"Порог негабарита: < {max_oversize}%. ВВ: {explosive.name}, порода: {rock.name}.")


if __name__ == "__main__":
    main()
