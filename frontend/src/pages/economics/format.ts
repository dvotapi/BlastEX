/**
 * Числа вкладки «Экономика блока» в русской записи.
 *
 * Одни и те же рубли на одной странице должны выглядеть одинаково: смета,
 * лестница цены, разложение бурения и сравнение прогонов печатают их
 * отсюда, а не каждая по-своему.
 */

/** Рубли: разделители тысяч, знаков после запятой по месту. */
export const money = (value: number, digits = 2) =>
  value.toLocaleString("ru-RU", { minimumFractionDigits: digits, maximumFractionDigits: digits });

/** Норма или количество: копеек не показывает, лишние нули не дописывает; с `digits` — ровно столько знаков. */
export const amount = (value: number, digits?: number) =>
  value.toLocaleString(
    "ru-RU",
    digits === undefined
      ? { maximumFractionDigits: 2 }
      : { minimumFractionDigits: digits, maximumFractionDigits: digits },
  );

/** Доля в процентах; пусто, если доля не пришла. */
export const percent = (share: number | undefined) =>
  share === undefined ? "" : `${(share * 100).toLocaleString("ru-RU", { maximumFractionDigits: 2 })} %`;

const rounded = (value: number, digits: number) => Number(value.toFixed(digits));

/** Больше знаков не бывает ни у нормы, ни у цены: дальше это шум, а не число. */
const MAX_DIGITS = 6;

/**
 * Норма и цена с таким числом знаков, чтобы их произведение давало
 * показанную сумму строки.
 *
 * Ради этого колонки и заведены: сметчик перемножает то, что видит. Двух
 * знаков хватает не всегда — цену модель иногда получает делением (литр ДТ
 * — из цены за тонну), а норму счётом (смены станка на блок), и при
 * округлении до сотых произведение расходится с суммой на рубли. Знаки
 * добавляются тому операнду, которому они нужнее, и ровно до тех пор, пока
 * расхождение не исчезнет.
 */
export function reconcilingColumns(
  quantity: number,
  price: number,
  amountRub: number,
): { quantity: string; price: string } {
  const shownAmount = Math.round(amountRub);
  for (let total = 4; total <= MAX_DIGITS * 2; total += 1) {
    for (let quantityDigits = 2; quantityDigits <= MAX_DIGITS; quantityDigits += 1) {
      const priceDigits = total - quantityDigits;
      if (priceDigits < 2 || priceDigits > MAX_DIGITS) continue;
      const product = rounded(quantity, quantityDigits) * rounded(price, priceDigits);
      if (Math.round(product) === shownAmount) {
        return {
          // Двух знаков хватило — значит хватит и обычной записи: «220 шт»
          // читается лучше, чем «220,00 шт». Лишние знаки дописываются
          // только там, где без них сумма не сходится.
          quantity: quantityDigits > 2 ? money(quantity, quantityDigits) : amount(quantity),
          price: money(price, priceDigits),
        };
      }
    }
  }
  // Сумма строки складывается не из этих двух чисел (ступени, доплата):
  // показываем их как есть, а объяснение сметчик раскроет формулой.
  return { quantity: amount(quantity), price: money(price) };
}

/**
 * Сумма на кубометр. Нулевой объём блока — прочерк, а не деление на
 * единицу: модель при пустом объёме цены обнуляет и предупреждает, и
 * интерфейс не вправе показывать вместо этого сумму строки.
 */
export const perM3 = (value: number, volume: number | null) =>
  volume === null ? "—" : `${money(value / volume)} ₽/м³`;
