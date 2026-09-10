/**
 * Раздел «Производственные услуги»: сверху строки модели этого раздела
 * (мобилизация/демобилизация, аренда склада ВМ — всё, что раздел `groupOf`
 * относит к SERVICES по `section === "VM_LOGISTICS"`, кроме ручных услуг
 * вкладки), под ними — панель ручных услуг вкладки (`ServicesPanel`,
 * задача 4) в неизменном виде: перенос услуги в справочник работает так
 * же, как и до конструктора сметы.
 *
 * Строки модели раздела не ищутся по одному захардкоженному коду статьи —
 * их несколько (`MOBILIZATION`, `UNIT_WAREHOUSE_RENT` и т. п.), и код
 * статьи не совпадает с кодом раздела `VM_LOGISTICS`. Рендерятся все строки
 * `group.lines`, кроме ручной услуги с вкладки (`quantity_origin ===
 * "MANUAL" && price_origin === "MANUAL"`) — так же, как `FuelSection`/
 * `FixedCostsSection` рендерят все строки своей группы.
 *
 * `busyServiceName`/`onMoveService` не входят в общий `SectionEditorProps` —
 * этот раздел единственный, кому они нужны, поэтому пропсы расширены здесь
 * же, тем же приёмом, каким `DrillingSection` добавляет свой
 * `onOpenDrillingPage`.
 */
import { EstimateLine } from "../estimate/EstimateLine";
import { ServicesPanel } from "../ServicesPanel";
import { lineNumber } from "../estimateModel";
import { lineShare } from "./lineHelpers";
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
  const modelLines = group.lines.filter(
    (line) => !(line.quantity_origin === "MANUAL" && line.price_origin === "MANUAL"),
  );

  return (
    <>
      {modelLines.map((line, index) => (
        <EstimateLine
          key={line.cost_item_code}
          number={lineNumber(group, index)}
          name={line.cost_item_name}
          origin={line.price_origin || line.quantity_origin}
          quantity={line.quantity}
          unit={line.unit}
          price={line.unit_price_rub}
          amount={line.amount_rub}
          volume={volume}
          share={lineShare(line, economics)}
          formula={line.formula}
        />
      ))}
      <ServicesPanel
        // Второй рубеж после `draftFromRun`: панель не обязана падать целиком,
        // если параметры пришли откуда-то ещё без списка услуг.
        services={params.services ?? []}
        operations={defaults.operations}
        canEdit={canEdit}
        busyCode={busyServiceName}
        onChange={(services) => onChange({ services })}
        onMove={onMoveService}
      />
    </>
  );
}
