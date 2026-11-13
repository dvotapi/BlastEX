"""Разделы проекта массового взрыва по форме ВМ.09.03 (TASK-018, PR 2).

Три раздела за флагом `mass_blast_v2`:

- «Проект МВ: реквизиты объекта» (`mass_blast_sites`, одна запись на объект) —
  удельный расход по типовому проекту и его обоснование, подписанты заказчика
  и подрядчика с основанием полномочий, профиль документов;
- «Профиль документов проекта МВ» (`mass_blast_profiles`) — тексты пунктов
  распорядка, сигналы и шаг округления массы заряда в таблице параметров;
- «Уведомления о массовом взрыве» (`blast_notifications`) — адресаты
  уведомления по п. 154 на каждый карьер: по одному уведомлению на адресата.

Проект МВ берёт значения из ревизии справочника, на которой он выпущен;
поле, заданное в самом проекте, главнее. Пустое поле профиля — текст формы
v0.11 по умолчанию (`design/mass_blast_schedule.py`).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from cost.v2.schemas.base import RefField, ReferencePayload, UnitField, field_error

__all__ = [
    "BlastNotificationPayload",
    "BlasterPayload",
    "TransportStaffPayload",
    "VehiclePayload",
    "MassBlastProfilePayload",
    "MassBlastSitePayload",
    "ScheduleText",
]

NotificationChannel = Literal["LETTER", "EMAIL", "PHONEGRAM"]
NotificationBasis = Literal["FNP", "CONTRACT", "CUSTOMER_RULES"]

_AUTHORITY_HINT = (
    "Приказ № и дата, если подписывает не технический руководитель (п. 414); "
    "пусто у такого подписанта — предупреждение"
)


class MassBlastSitePayload(ReferencePayload):
    site_code: str = RefField(
        "sites", title="Объект", description="Карьер, к которому относятся реквизиты; одна запись на объект"
    )
    tp_basis: str = Field(
        default="",
        title="Типовой проект БВР",
        description="На основании какого типового проекта составляется проект массового взрыва: №, редакция, дата",
        max_length=300,
    )
    q_tp_kg_m3: Decimal | None = UnitField(
        "кг/м³",
        title="Удельный расход ВВ по типовому проекту",
        description="Проектный q; отклонение расчётного больше 10 % требует обоснования (п. 411)",
        default=None,
        gt=0,
        le=10,
    )
    q_tp_source: str = Field(
        default="",
        title="Документ — источник удельного расхода",
        description="Где взят проектный q: документ, таблица, страница",
        max_length=300,
    )
    q_just: str = Field(
        default="",
        title="Обоснование удельного расхода",
        description="Печатается в техрасчёте, если расчётный q отличается от проектного больше чем на 10 % (п. 411)",
        max_length=600,
    )

    # Подписанты (п. 414): «СОГЛАСОВАНО» и левое «УТВЕРЖДАЮ» распорядка — заказчик,
    # «УТВЕРЖДАЮ» проекта и правое распорядка — подрядчик.
    customer_approver_position: str = Field(
        default="", title="Заказчик: должность подписанта", description="Технический руководитель заказчика", max_length=200
    )
    customer_approver_name: str = Field(
        default="", title="Заказчик: фамилия, инициалы", description="Подписант заказчика", max_length=120
    )
    customer_approver_is_head: bool = Field(
        default=True,
        title="Заказчик: подписант — технический руководитель",
        description="Снимите, если подписывает лицо, назначенное приказом (п. 414)",
    )
    customer_approver_authority: str = Field(
        default="", title="Заказчик: основание полномочий", description=_AUTHORITY_HINT, max_length=200
    )
    contractor_approver_position: str = Field(
        default="", title="Подрядчик: должность подписанта", description="Технический руководитель подрядчика", max_length=200
    )
    contractor_approver_name: str = Field(
        default="", title="Подрядчик: фамилия, инициалы", description="Подписант подрядчика", max_length=120
    )
    contractor_approver_is_head: bool = Field(
        default=True,
        title="Подрядчик: подписант — технический руководитель",
        description="Снимите, если подписывает лицо, назначенное приказом (п. 414)",
    )
    contractor_approver_authority: str = Field(
        default="", title="Подрядчик: основание полномочий", description=_AUTHORITY_HINT, max_length=200
    )
    customer_tech_contact: str = Field(
        default="",
        title="Заказчик: адрес, ФИО и телефон технического руководителя",
        description="Графа уведомления о массовом взрыве (п. 154)",
        max_length=300,
    )
    contract_no: str = Field(
        default="", title="Договор подряда: №", description="Акт приёмки выполненных работ (TASK-018 §2)", max_length=80
    )
    contract_date: str = Field(
        default="", title="Договор подряда: дата", description="ДД.ММ.ГГГГ — в шапке акта приёмки", max_length=10
    )
    acceptance_appendix_no: str = Field(
        default="", title="Акт приёмки: № приложения к договору", description="«Приложение № … к договору»", max_length=20
    )
    customer_responsible: str = Field(
        default="",
        title="Заказчик: ответственное лицо по приёмке",
        description="Должность, фамилия и инициалы — в комиссии акта приёмки выполненных работ",
        max_length=300,
    )
    # Наряд-путёвка (TASK-018 PR 6, В7): постоянные для объекта поля выписки.
    blasting_permit: str = Field(
        default="",
        title="Разрешение на ведение взрывных работ",
        description="№ и дата разрешения — в шапке наряда-путёвки",
        max_length=300,
    )
    warehouse: str = Field(
        default="", title="Склад выдачи ВМ", description="Склад, с которого выдаются ВМ по наряду-путёвке", max_length=200
    )
    vehicle: str = Field(
        default="", title="Спецавтомобиль", description="Марка и гос. номер автомобиля для перевозки ВМ", max_length=200
    )
    driver: str = Field(default="", title="Водитель", description="Фамилия, инициалы водителя спецавтомобиля", max_length=200)
    # Наряд-путёвка ↔ MagEX (TASK-018 PR 7, решения В3, В4): № и дата разрешения,
    # марка и гос. номер раздельно — так их ждёт выписка; строки выше — запасные для печати.
    blasting_permit_number: str = Field(
        default="", title="Разрешение на ВР: №", description="Номер разрешения на ведение взрывных работ", max_length=200
    )
    blasting_permit_date: date | None = Field(
        default=None, title="Разрешение на ВР: дата", description="Дата выдачи разрешения на ведение взрывных работ"
    )
    vehicle_model: str = Field(
        default="", title="Спецавтомобиль: марка", description="Марка и модель автомобиля для перевозки ВМ", max_length=200
    )
    vehicle_plate: str = Field(
        default="", title="Спецавтомобиль: гос. номер", description="Государственный регистрационный номер", max_length=200
    )
    magex_warehouse_id: UUID | None = Field(
        default=None,
        title="Склад MagEX",
        description="Идентификатор склада выдачи в MagEX (карточка склада в MagEX); по нему наряд-путёвка резервирует ВМ",
    )
    # Постоянные места и средства распорядка (TASK-018 PR 6, В8).
    station: str = Field(
        default="", title="Место взрывной станции", description="Пункт 11 распорядка", max_length=300
    )
    shelter: str = Field(default="", title="Место укрытия", description="Где укрываются люди при взрыве", max_length=300)
    gather: str = Field(default="", title="Место сбора", description="Место сбора людей после вывода из опасной зоны", max_length=300)
    exit_route: str = Field(
        default="", title="Куда удаляются люди", description="Направление вывода людей из опасной зоны", max_length=300
    )
    siren: str = Field(default="", title="Средство подачи сигналов", description="Сирена, громкоговоритель (п. 163)", max_length=200)
    transport: str = Field(default="", title="Транспорт ВМ", description="Чем доставляются ВМ на блок", max_length=200)
    cleaning: str = Field(default="", title="Средства очистки скважин", description="Чем очищаются скважины перед заряжанием", max_length=200)
    profile_code: str | None = RefField(
        "mass_blast_profiles",
        title="Профиль документов",
        description="Тексты распорядка и правила таблицы параметров; пусто — тексты формы ВМ.09.03 по умолчанию",
        default=None,
    )


class ScheduleText(ReferencePayload):
    point: str = Field(
        title="Пункт",
        description="Номер пункта распорядка, как в форме: «16», «29.1»",
        pattern=r"^\d{1,2}(\.\d{1,2})?$",
    )
    title: str = Field(default="", title="Наименование", description="Пусто — наименование формы", max_length=300)
    value: str = Field(
        default="",
        title="Текст",
        description="Постоянный текст пункта; пусто — текст формы. Пункты со значениями проекта текстом не заменяются",
        max_length=600,
    )


class MassBlastProfilePayload(ReferencePayload):
    charge_round_kg: Decimal = UnitField(
        "кг",
        title="Округление массы заряда",
        description="Масса заряда в таблице параметров округляется до этого шага; итоги — по округлённым",
        default=Decimal("5"),
        gt=0,
        le=50,
    )
    signal_warning: str = Field(
        default="", title="Предупредительный сигнал", description="п. 163; пусто — «один продолжительный»", max_length=120
    )
    signal_combat: str = Field(
        default="", title="Боевой сигнал", description="п. 163; пусто — «два продолжительных»", max_length=120
    )
    signal_clear: str = Field(
        default="", title="Сигнал отбоя", description="п. 163; пусто — «три коротких»", max_length=120
    )
    letterhead: str = Field(
        default="",
        title="Бланк Общества",
        description="Строки шапки уведомления о массовом взрыве: полное наименование, ИНН и КПП, адрес, телефон, "
        "почта — каждая с новой строки; пусто — только краткое наименование",
        max_length=600,
    )
    acceptance_text: str = Field(
        default="",
        title="Текст акта приёмки по договору",
        description="Абзацы между «составили настоящий акт» и «К оплате принимаются»; подстановки {блок}, "
        "{горизонт}, {дата взрыва}; пусто — текст формы ВМ.09.03",
        max_length=2000,
    )
    schedule_texts: list[ScheduleText] = Field(
        default_factory=list,
        title="Тексты пунктов распорядка",
        description="Замена наименований и постоянных текстов пунктов формы; не указанные пункты — как в форме",
        max_length=60,
    )

    @model_validator(mode="after")
    def _unique_points(self) -> "MassBlastProfilePayload":
        seen: set[str] = set()
        for index, row in enumerate(self.schedule_texts):
            if row.point in seen:
                field_error(type(self), ("schedule_texts", index, "point"), "Пункт уже есть в профиле", row.point)
            seen.add(row.point)
        return self


class BlastNotificationPayload(ReferencePayload):
    site_code: str = RefField("sites", title="Объект", description="Карьер, о взрывах на котором уведомляется адресат")
    recipient_position: str = Field(
        title="Адресат — должность, орган",
        description="Кому направляется уведомление (п. 154)",
        min_length=1,
        max_length=300,
    )
    recipient_name: str = Field(
        default="", title="Адресат — фамилия, инициалы", description="В дательном падеже", max_length=120
    )
    salutation: str = Field(default="", title="Обращение", description="«Уважаемый …!»", max_length=200)
    channel: NotificationChannel = Field(
        default="LETTER", title="Способ", description="Письмо, электронная почта или телефонограмма"
    )
    lead_days: int = UnitField(
        "сут", title="Срок", description="За сколько суток до взрыва направляется уведомление", default=1, ge=0, le=30
    )
    basis: NotificationBasis = Field(
        default="FNP", title="Основание", description="ФНП 494 п. 154, договор или регламент заказчика"
    )
    signer: str = Field(
        default="", title="Подписывает", description="Должность, фамилия, инициалы подписанта", max_length=200
    )

    @model_validator(mode="after")
    def _name_or_position(self) -> "BlastNotificationPayload":
        if not self.recipient_position.strip():
            field_error(type(self), "recipient_position", "Укажите адресата уведомления", self.recipient_position)
        return self


class BlasterPayload(ReferencePayload):
    """Взрывник для наряда-путёвки (TASK-018 PR 7, решение В2): ФИО — наименование записи.

    MagEX узнаёт взрывника по постоянному UUID (`blaster.ref`): сотрудник
    SafetyMAIN, а пока его нет — UUID, который BlastEX выводит из организации
    и индекса. После выдачи ВМ взрывник наряда не меняется.
    """

    blaster_index: str = Field(
        title="Индивидуальный индекс",
        description="Индекс взрывника по единой книжке взрывника — печатается в наряде-путёвке",
        min_length=1,
        max_length=200,
    )
    book_number: str = Field(default="", title="№ единой книжки взрывника", description="Номер книжки", max_length=80)
    employee_ref: UUID | None = Field(
        default=None,
        title="Сотрудник SafetyMAIN",
        description="Постоянный идентификатор сотрудника в SafetyMAIN; пусто — BlastEX присвоит постоянный по индексу",
    )


class VehiclePayload(ReferencePayload):
    """Спецавтомобиль для перевозки ВМ (наряд-путёвка): выбирается в наряде списком и
    подставляет марку, гос. номер и водителя по умолчанию. Наименование — как называют
    машину на объекте."""

    vehicle_model: str = Field(
        title="Марка, модель", description="Марка и модель автомобиля — печатается в наряде-путёвке",
        min_length=1, max_length=200,
    )
    vehicle_plate: str = Field(
        title="Гос. номер", description="Государственный регистрационный номер", min_length=1, max_length=200,
    )
    driver: str = Field(
        default="", title="Водитель по умолчанию", description="Фамилия, инициалы — подставляются в наряд, можно поменять",
        max_length=200,
    )


TransportRole = Literal["DRIVER", "ESCORT", "BOTH"]


class TransportStaffPayload(ReferencePayload):
    """Водитель спецавтомобиля или сопровождающее лицо при перевозке ВМ: ФИО — наименование
    записи. В наряде выбирается списком «Водитель» или «Сопровождающее лицо» по роли."""

    role: TransportRole = Field(
        default="DRIVER", title="Роль", description="Водитель, сопровождающий или и то и другое",
    )
    position: str = Field(default="", title="Должность", description="Должность работника", max_length=200)
    document: str = Field(
        default="", title="Удостоверение, допуск", description="№ и дата удостоверения или допуска к перевозке ВМ",
        max_length=200,
    )
