import { useEffect, useId, useState } from "react";
import { maxUnderchargeM, type PanelInputs } from "./calcInputs";
import { VariantMarker } from "./VariantMarker";

/**
 * Параметры одного варианта заряда: тип ВВ, недозаряд, замедление,
 * детонаторы и НСИ. Поля живут своим состоянием, засеянным `initialInputs`
 * один раз (новые значения — пересоздание через `key`), и каждое изменение,
 * включая первое на монтировании, уходит наверх через `onInputsChange`: из
 * этих значений лист считает схему заряда и сохраняет свои настройки.
 */
export function HoleVariantCard({
  variantLabel,
  color,
  depthM,
  explosives,
  nsiLengthOptions,
  detonatorDelayOptions,
  initialInputs,
  onInputsChange,
}: {
  variantLabel: string;
  /** Цвет ВВ варианта — маркер в карточке и в заголовках таблиц сравнения. */
  color: string;
  /** Глубина скважины: предел недозаряда. */
  depthM: number;
  explosives: { id?: string; key: string; name: string }[];
  nsiLengthOptions: number[];
  detonatorDelayOptions: number[];
  initialInputs: PanelInputs;
  onInputsChange: (inputs: PanelInputs) => void;
}) {
  const id = useId();
  const [explosiveKey, setExplosiveKey] = useState(initialInputs.explosive_key);
  const [underchargeM, setUnderchargeM] = useState(Math.min(initialInputs.undercharge_m, maxUnderchargeM(depthM)));
  const [intermediateDetonators, setIntermediateDetonators] = useState(initialInputs.intermediate_detonators_per_hole);
  const [nsiPerHole, setNsiPerHole] = useState(initialInputs.nsi_per_hole);
  const [nsiLength1M, setNsiLength1M] = useState(initialInputs.nsi_length_1_m);
  const [nsiLength2M, setNsiLength2M] = useState(initialInputs.nsi_length_2_m);
  const [delayMs, setDelayMs] = useState(initialInputs.detonator_delay_ms);

  useEffect(() => {
    onInputsChange({
      explosive_key: explosiveKey,
      undercharge_m: underchargeM,
      intermediate_detonators_per_hole: intermediateDetonators,
      nsi_per_hole: nsiPerHole,
      nsi_length_1_m: nsiLength1M,
      nsi_length_2_m: nsiLength2M,
      detonator_delay_ms: delayMs,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [explosiveKey, underchargeM, intermediateDetonators, nsiPerHole, nsiLength1M, nsiLength2M, delayMs]);

  const maxUndercharge = maxUnderchargeM(depthM);
  const shownUndercharge = Math.min(underchargeM, maxUndercharge);

  return (
    <div className="vcard" aria-labelledby={`${id}-title`} role="group">
      <div className="vcard-head" id={`${id}-title`}>
        <VariantMarker color={color} />
        {variantLabel}
      </div>
      <div className="vcard-grid">
        <label>
          Тип ВВ
          <select value={explosiveKey} onChange={(e) => setExplosiveKey(e.target.value)}>
            {explosives.map((item) => (
              <option key={item.id || item.key} value={item.key}>{item.name}</option>
            ))}
          </select>
        </label>
        <label className="vcard-range">
          <span className="vcard-range-top"><span>Недозаряд, м</span><b>{shownUndercharge.toFixed(1)}</b></span>
          <input
            type="range"
            min={0}
            max={maxUndercharge}
            step={0.1}
            value={shownUndercharge}
            onChange={(e) => setUnderchargeM(Number(e.target.value))}
          />
        </label>
        <label>
          Замедление, мс
          <select value={delayMs} onChange={(e) => setDelayMs(Number(e.target.value))}>
            {detonatorDelayOptions.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </label>
        <label>
          Пром. детонаторы
          <select value={intermediateDetonators} onChange={(e) => setIntermediateDetonators(Number(e.target.value))}>
            <option value={1}>1</option>
            <option value={2}>2</option>
          </select>
        </label>
        <label>
          Скважинное НСИ
          <select value={nsiPerHole} onChange={(e) => setNsiPerHole(Number(e.target.value))}>
            <option value={1}>1 устройство/скв</option>
            <option value={2}>2 (дублирование)</option>
          </select>
        </label>
        <label>
          Длина НСИ-1, м
          <select value={nsiLength1M} onChange={(e) => setNsiLength1M(Number(e.target.value))}>
            {nsiLengthOptions.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </label>
        {nsiPerHole === 2 && (
          <label>
            Длина НСИ-2, м
            <select value={nsiLength2M} onChange={(e) => setNsiLength2M(Number(e.target.value))}>
              {nsiLengthOptions.map((value) => <option key={value} value={value}>{value}</option>)}
            </select>
          </label>
        )}
      </div>
    </div>
  );
}
