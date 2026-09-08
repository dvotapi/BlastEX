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

/** Норма или количество: копеек не показывает, лишние нули не дописывает. */
export const amount = (value: number) =>
  value.toLocaleString("ru-RU", { maximumFractionDigits: 2 });

/** Доля в процентах; пусто, если доля не пришла. */
export const percent = (share: number | undefined) =>
  share === undefined ? "" : `${(share * 100).toLocaleString("ru-RU", { maximumFractionDigits: 2 })} %`;

/**
 * Сумма на кубометр. Нулевой объём блока — прочерк, а не деление на
 * единицу: модель при пустом объёме цены обнуляет и предупреждает, и
 * интерфейс не вправе показывать вместо этого сумму строки.
 */
export const perM3 = (value: number, volume: number | null) =>
  volume === null ? "—" : `${money(value / volume)} ₽/м³`;
