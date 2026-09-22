import { ruNumber } from "../../../lib/format";
import examples from "./helpExamples.json";
import { gridText, qDeltaText, trimmed } from "./kuzramFormat";

const SOURCE_URL =
  "https://www.smctesting.com/documents/mine-to-mill/The%20kuz%20ram%20fragmentation%20model%2020%20years%20on.pdf";

const METHOD_NAMES: Record<string, string> = {
  rmd50: "Монолитный массив (RMD 50)",
  rmd10: "Раздробленная порода (RMD 10)",
  joint_factor: "По трещиноватости (JF)",
};

const FORMULAS = `d   = коронка / 1000 · коэффициент разбуривания          [м]
L   = 0,8 · (H + перебур)                                   [м]
Q   = π·d²/4 · ρВВ · 1000 · L                               [кг]
V   = Q / q;   W = √(V / (a/W · H));   a = a/W · W;   b = W
RE  = теплота взрыва / 4,184                                (к тротилу)

RDI = 25·ρ − 50;   HF = UCS / 5
RMD = 50 | 10 | JF;   JF = JCF·JPS + JPA
JPS = 10 при s < 0,1 м; 20 при s < 0,3 м; 80 при s < 0,95·P; иначе 50
      s = 1 / трещиноватость;   P = √(a·b)
A   = 0,06 · (RMD + RDI + HF) · C(A)
x50 = A · q^−0,8 · Q^(1/6) · RE^(−e) · 10                  [мм], e = 19/20 или 19/30
n   = (2,2 − 14·W/d[мм]) · √((1 + a/W)/2) · (1 − σ/W) · 1,1^0,1 · min(1, L/H) · C(n),  n ≥ 0,1
xc  = x50 / (ln 2)^(1/n)
негабарит = exp(−(кусок / xc)^n) · 100 %`;

/**
 * Вкладка «Как пользоваться» окна «Модель Kuz-Ram». Цифры примеров — из
 * helpExamples.json; tests/test_kuzram_help_examples.py пересчитывает их
 * моделью, поэтому текст не расходится с расчётом. Меняя пример, меняйте
 * JSON, а не цифры в тексте.
 */
export function KuzRamHelp() {
  const { source, basic, calibration, methods, not_reached: notReached, joint_switch: jointSwitch } = examples;
  const methodQs = methods.rows.map((row) => row.q_kg_m3);
  const jf = methods.rows.find((row) => row.rock_factor_method === "joint_factor");

  return (
    <div className="kuzram-help">
      <section aria-labelledby="kuzram-help-what">
        <h3 id="kuzram-help-what">Что делает модель</h3>
        <p>
          Для каждой выбранной коронки модель ищет наименьший удельный расход ВВ q, при котором доля негабарита не
          превышает допустимую. q перебирается с шагом 0,01 кг/м³ от 0,10 до верхней границы перебора (по умолчанию 2,0).
        </p>
        <p>
          При каждом q считаются заряд скважины Q, объём на скважину V = Q/q и сетка: линия наименьшего сопротивления W и
          шаг a = a/W · W. Затем по формулам Kuz-Ram — средний кусок x50 (половина массы взорванной породы мельче него),
          индекс равномерности n (чем он больше, тем однороднее куски) и негабарит — доля кусков крупнее кондиционного.
        </p>
        <p>
          Формулы — по статье К. Каннингема «The Kuz-Ram fragmentation model — 20 years on» (2005). Всё считает сервер;
          окно показывает результат и хранит настройки за объектом работ.
        </p>
      </section>

      <section aria-labelledby="kuzram-help-order">
        <h3 id="kuzram-help-order">Порядок работы</h3>
        <ol>
          <li>На листе задайте породу, ВВ, уступ, перебур, кондиционный кусок, допустимый негабарит и коронки — окно берёт исходные данные оттуда.</li>
          <li>Выберите способ расчёта фактора породы A. Без документации трещин оставьте «Монолитный массив (RMD 50)».</li>
          <li>Сравните столбцы «Kuz-Ram» и «До исправления». Большая разница — повод проверить свойства породы.</li>
          <li>Внесите фактические взрывы: коронку, фактический удельный расход и фактический негабарит.</li>
          <li>Нажмите «Подобрать C(A) по факту» — поправка запишется в настройки объекта, варианты пересчитаются.</li>
          <li>Проверьте сетку выбранной коронки и разбор расчёта.</li>
          <li>Нажмите «Перенести в проект» или сохраните паспорт — как обычно на листе.</li>
        </ol>
      </section>

      <section aria-labelledby="kuzram-help-settings">
        <h3 id="kuzram-help-settings">Настройки</h3>
        <dl>
          <dt>Фактор породы A</dt>
          <dd>
            Насколько порода сопротивляется дроблению: A = 0,06·(RMD + RDI + HF). RDI = 25·ρ − 50 учитывает плотность,
            HF = UCS/5 — прочность на сжатие. RMD описывает массив: 50 — монолитный (трещины реже скважин), 10 —
            раздробленный; JF — по трещиноватости из справочника пород. «Задать вручную» — A из опыта или отчёта, от 0,5
            до 30. Умолчание — RMD 50.
          </dd>
          <dt>Как выбрать способ A</dt>
          <dd>
            Без достоверной документации трещин и их ориентации оставляйте RMD 50 и уточняйте поправку C(A) по
            фактическим взрывам. JF выбирайте, только когда трещины задокументированы: способ чувствителен к шагу трещин
            и может дать q заметно выше (пример ниже).
          </dd>
          <dt>Состояние трещин JCF и ориентация JPA</dt>
          <dd>
            Только для способа JF: JF = JCF·JPS + JPA. JCF: плотные — 1, раскрытые — 1,5, с заполнителем — 2. JPA — по
            Каннингему: падение трещин в сторону откоса — 20, простирание поперёк откоса — 30, падение в массив — 40.
            JPS модель берёт из шага трещин и сетки.
          </dd>
          <dt>Поправка C(A)</dt>
          <dd>
            Множитель к A, от 0,1 до 10, умолчание 1 — без поправки. Больше 1 — порода дробится хуже, чем предсказывает
            формула, и q растёт. Подбирается по фактическим взрывам.
          </dd>
          <dt>Показатель при силе ВВ</dt>
          <dd>19/20 — Каннингем, 1987 (умолчание); 19/30 — вариант 1983 года, как в расчёте «до исправления». С 19/30 сила ВВ меньше влияет на средний кусок.</dd>
          <dt>Отклонение бурения σ, м</dt>
          <dd>Стандартное отклонение забоя скважины от проекта, от 0 до 2 м, умолчание 0. Чем больше σ, тем неоднороднее куски и тем выше q.</dd>
          <dt>Поправка C(n)</dt>
          <dd>Множитель к индексу равномерности n, от 0,5 до 2, умолчание 1. Меняйте, только если есть данные рассева.</dd>
          <dt>Верхняя граница перебора q</dt>
          <dd>От 0,5 до 5 кг/м³, умолчание 2,0. Если порог негабарита не достигнут и на ней, q остаётся на границе, а в таблицах появляется значок «!».</dd>
        </dl>
      </section>

      <section aria-labelledby="kuzram-help-read">
        <h3 id="kuzram-help-read">Как читать результаты</h3>
        <ul>
          <li><b>Сводка</b> — выбранная коронка: q, сетка и негабарит обеих моделей и разница q в процентах (Kuz-Ram относительно «до исправления»).</li>
          <li><b>Таблица</b> — строка на коронку; выбор строки меняет выбранную коронку и на листе.</li>
          <li><b>«До исправления»</b> — прежний расчёт: фактор A по формуле 1983 года, диаметр в индексе n в метрах (n всегда 0,8), перебор q от 0,30 до 1,50. Нужен на переходный период, чтобы видеть, насколько изменились рекомендации.</li>
          <li><b>Значок «!»</b> — порог негабарита не достигнут даже на верхней границе перебора q. Если округлённый негабарит совпал с порогом, вместо числа стоит «{">"} порога».</li>
          <li><b>«≤ 0,10»</b> — порог выполнен уже при наименьшем q; меньшие значения модель не проверяет.</li>
          <li><b>График</b> — q по коронкам обеих моделей; полая точка — порог не достигнут, ромб — фактический взрыв.</li>
          <li><b>Разбор расчёта</b> — промежуточные величины выбранной коронки для обеих моделей. У n два числа «сырое → принятое»: если формула даёт меньше 0,1 (нереальная геометрия или σ не меньше W), принимается 0,1; в расчёте «до исправления» n не бывает меньше 0,8.</li>
          <li><b>W/d</b> — ЛНС к диаметру скважины. Каннингем рекомендует 25–35; выше 35 окно предупреждает, что сетка редкая для этого диаметра и прогноз менее надёжен. Подбор q это не ограничивает, а ниже 25 для крепких пород — обычная сетка.</li>
        </ul>
      </section>

      <section aria-labelledby="kuzram-help-examples">
        <h3 id="kuzram-help-examples">Примеры</h3>
        <p>
          Во всех примерах, кроме последнего: {source.rock.name}, {source.explosive.name}, уступ {trimmed(source.target.bench_height_m)} м,
          перебур {trimmed(source.target.overdrill_m)} м, кондиционный кусок {trimmed(source.target.lump_size_mm)} мм, допустимый
          негабарит {trimmed(source.max_oversize_threshold_pct)} %.
        </p>

        <section aria-labelledby="kuzram-example-basic">
          <h4 id="kuzram-example-basic">Базовый расчёт</h4>
          <p>
            Коронка {trimmed(basic.crown_mm)} мм. Kuz-Ram: q {ruNumber(basic.kuzram.q_kg_m3, 2)} кг/м³, сетка{" "}
            {gridText(basic.kuzram.grid_a_m, basic.kuzram.grid_b_m)} м, негабарит {ruNumber(basic.kuzram.oversize_pct, 2)} %. До
            исправления: q {ruNumber(basic.legacy.q_kg_m3, 2)} кг/м³, сетка {gridText(basic.legacy.grid_a_m, basic.legacy.grid_b_m)} м,
            негабарит {ruNumber(basic.legacy.oversize_pct, 2)} %. Разница q — {qDeltaText(basic.kuzram.q_kg_m3, basic.legacy.q_kg_m3)}:
            две главные ошибки прежнего расчёта почти гасят друг друга, поэтому для монолитного массива рекомендации меняются мало.
          </p>
        </section>

        <section aria-labelledby="kuzram-example-calibration">
          <h4 id="kuzram-example-calibration">Подбор C(A) по фактическим взрывам</h4>
          <p className="example-note">Взрывы условные — только для иллюстрации.</p>
          <table className="kuzram-table">
            <thead>
              <tr>
                <th scope="col">Коронка, мм</th>
                <th scope="col">q факт, кг/м³</th>
                <th scope="col">Негабарит факт, %</th>
                <th scope="col">Kuz-Ram при C(A) = 1, %</th>
                <th scope="col">C(A) строки</th>
              </tr>
            </thead>
            <tbody>
              {calibration.facts.map((fact, index) => (
                <tr key={index}>
                  <td>{trimmed(fact.crown_mm)}</td>
                  <td>{ruNumber(fact.q_kg_m3, 2)}</td>
                  <td>{ruNumber(fact.oversize_pct, 1)}</td>
                  <td>{ruNumber(calibration.rows[index].model_oversize_pct, 2)}</td>
                  <td>{trimmed(calibration.rows[index].rock_factor_correction)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p>
            Фактический негабарит выше прогноза — порода дробится хуже, чем по формуле, поэтому C(A) больше 1. Итог —
            среднее геометрическое по строкам: C(A) = {trimmed(calibration.rock_factor_correction)}. После подбора коронка{" "}
            {trimmed(calibration.crown_mm)} мм: q {ruNumber(basic.kuzram.q_kg_m3, 2)} → {ruNumber(calibration.after.q_kg_m3, 2)} кг/м³,
            сетка {gridText(basic.kuzram.grid_a_m, basic.kuzram.grid_b_m)} → {gridText(calibration.after.grid_a_m, calibration.after.grid_b_m)} м.
          </p>
        </section>

        <section aria-labelledby="kuzram-example-methods">
          <h4 id="kuzram-example-methods">Выбор способа расчёта A</h4>
          <table className="kuzram-table">
            <thead>
              <tr>
                <th scope="col">Способ</th>
                <th scope="col">RMD или JF</th>
                <th scope="col">A</th>
                <th scope="col">q, кг/м³</th>
                <th scope="col">Сетка a × b, м</th>
              </tr>
            </thead>
            <tbody>
              {methods.rows.map((row) => (
                <tr key={row.rock_factor_method}>
                  <td>{METHOD_NAMES[row.rock_factor_method]}</td>
                  <td>{trimmed(row.rmd)}</td>
                  <td>{ruNumber(row.rock_factor_a, 2)}</td>
                  <td>{ruNumber(row.q_kg_m3, 2)}</td>
                  <td>{gridText(row.grid_a_m, row.grid_b_m)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p>
            Коронка {trimmed(methods.crown_mm)} мм, те же исходные данные — а q различается в{" "}
            {trimmed(Math.max(...methodQs) / Math.min(...methodQs), 1)} раза: всё решает оценка массива. Трещиноватость{" "}
            {trimmed(source.rock.fissuring_ff)} на 1 м из справочника даёт JF = {trimmed(jf?.rmd ?? 0)} против RMD 50 у
            монолитного массива. Без документации трещин надёжнее RMD 50 и поправка C(A) по фактическим взрывам.
          </p>
        </section>

        <section aria-labelledby="kuzram-example-not-reached">
          <h4 id="kuzram-example-not-reached">Порог не достигнут</h4>
          <p>
            Коронка {trimmed(notReached.crown_mm)} мм, верхняя граница перебора {trimmed(notReached.low.q_max_kg_m3)} кг/м³: даже при q{" "}
            {ruNumber(notReached.low.q_kg_m3, 2)} негабарит {ruNumber(notReached.low.oversize_pct, 2)} % больше допустимых{" "}
            {trimmed(source.max_oversize_threshold_pct)} % — в таблицах значок «!», точка на графике полая. Что делать: поднять
            верхнюю границу (при {trimmed(notReached.raised.q_max_kg_m3)} подбор даёт q {ruNumber(notReached.raised.q_kg_m3, 2)} и
            негабарит {ruNumber(notReached.raised.oversize_pct, 2)} %), взять меньшую коронку или проверить порог и кондиционный кусок.
          </p>
        </section>

        <section aria-labelledby="kuzram-example-joint-switch">
          <h4 id="kuzram-example-joint-switch">Скачок при способе JF</h4>
          <p>
            Тот же {source.rock.name.toLowerCase()}, но с редкими трещинами — {trimmed(jointSwitch.fissuring_ff)} на 1 м (шаг{" "}
            {ruNumber(jointSwitch.joint_spacing_m, 2)} м), коронка {trimmed(jointSwitch.crown_mm)} мм, способ JF. При q{" "}
            {ruNumber(jointSwitch.before.q_kg_m3, 2)} приведённая сетка P = {ruNumber(jointSwitch.before.reduced_pattern_m, 2)} м,
            шаг трещин меньше 0,95·P — JPS = {trimmed(jointSwitch.before.jps)}, A = {ruNumber(jointSwitch.before.rock_factor_a, 2)},
            негабарит {ruNumber(jointSwitch.before.oversize_pct, 2)} %. При q {ruNumber(jointSwitch.after.q_kg_m3, 2)} сетка чуть
            плотнее, P = {ruNumber(jointSwitch.after.reduced_pattern_m, 2)} м, и 0,95·P становится меньше шага трещин: JPS падает до{" "}
            {trimmed(jointSwitch.after.jps)}, A — до {ruNumber(jointSwitch.after.rock_factor_a, 2)}, и негабарит скачком падает до{" "}
            {ruNumber(jointSwitch.after.oversize_pct, 2)} %. Подбор останавливается на {ruNumber(jointSwitch.after.q_kg_m3, 2)}:
            негабарит заметно ниже порога, а q соседних коронок может отличаться сильнее обычного. Это свойство ступенчатой
            таблицы JPS у Каннингема, а не ошибка расчёта.
          </p>
        </section>
      </section>

      <details>
        <summary>Формулы и источники</summary>
        <pre>{FORMULAS}</pre>
        <p>
          Источник: C. V. B. Cunningham,{" "}
          <a href={SOURCE_URL} target="_blank" rel="noreferrer">
            «The Kuz-Ram fragmentation model — 20 years on»
          </a>
          , EFEE, 2005. Вкладка «Проектирование», отчёты и ML-калибровка пока считают по прежней модели.
        </p>
      </details>
    </div>
  );
}
