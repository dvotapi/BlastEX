/**
 * Раздел «Производственные услуги»: сверху строка доставки и хранения ВМ
 * (считана моделью по паспорту), под ней — панель ручных услуг вкладки
 * (`ServicesPanel`, задача 4) в неизменном виде: перенос услуги в справочник
 * работает так же, как и до конструктора сметы.
 *
 * `busyServiceName`/`onMoveService` не входят в общий `SectionEditorProps` —
 * этот раздел единственный, кому они нужны, поэтому пропсы расширены здесь
 * же, тем же приёмом, каким `DrillingSection` добавляет свой
 * `onOpenDrillingPage`.
 */
import { EstimateLine } from "../estimate/EstimateLine";
import { ServicesPanel } from "../ServicesPanel";
import { lineNumber } from "../estimateModel";
import { lineByCode, lineShare } from "./lineHelpers";
import type { SectionEditorProps } from "./types";

export type ServicesSectionProps = SectionEditorProps & {
  /** Название услуги, которая сейчас переносится в справочник. */
  busyServiceName: string;
  onMoveService: (index: number) => void;
};

export function ServicesSection({
  group,
  params,
  defaults,
  economics,
  volume,
  canEdit,
  onChange,
  busyServiceName,
  onMoveService,
}: ServicesSectionProps) {
  const logistics = lineByCode(group.lines, "VM_LOGISTICS");

  return (
    <>
      {logistics && (
        <EstimateLine
          number={lineNumber(group, 0)}
          name={logistics.cost_item_name}
          origin={logistics.price_origin || logistics.quantity_origin}
          quantity={logistics.quantity}
          unit={logistics.unit}
          price={logistics.unit_price_rub}
          amount={logistics.amount_rub}
          volume={volume}
          share={lineShare(logistics, economics)}
          formula={logistics.formula}
        />
      )}
      <ServicesPanel
        services={params.services}
        operations={defaults.operations}
        canEdit={canEdit}
        busyCode={busyServiceName}
        onChange={(services) => onChange({ services })}
        onMove={onMoveService}
      />
    </>
  );
}
