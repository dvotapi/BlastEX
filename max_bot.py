# Общая идея:
# - MaxBotClient: тонкая обёртка над HTTP API MAX (GET /updates, POST /messages,
#   POST /answers). Все запросы идут на API_BASE и подписываются заголовком
#   Authorization: <token>.
# - BlastexMaxBot: “логика бота” + простая машина состояний (Step) для заполнения
#   заявки по шагам в диалоге с пользователем.
# - run(): бесконечный long polling цикл, который читает updates и отправляет их
#   в dispatch().


# shebang — позволяет запускать как исполняемый файл в Unix.
#!/usr/bin/env python3
"""
Бот MAX (https://dev.max.ru/docs-api) для приёма заявок заказчика на буровые и взрывные работы.

Запуск:
  export MAX_BOT_TOKEN="ваш_токен_из_business.max.ru"
  python max_bot.py

Long polling (GET /updates) подходит для разработки и теста; для production рекомендуется webhook.
"""

from __future__ import annotations # future import — включает аннотации типов как строки (удобно для Python<3.11).

# импорты библиотек
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import requests

API_BASE = "https://platform-api.max.ru" # API_BASE — корень API MAX (platform-api.max.ru).
LOG_PATH = Path(__file__).resolve().parent / "max_bot.log" # LOG_PATH — файл логов рядом со скриптом.
REQUESTS_JSONL = Path(__file__).resolve().parent / "data" / "max_requests.jsonl" # REQUESTS_JSONL — куда складываем заявки (jsonl: 1 строка = 1 JSON объект).
# Справочники по user_id (закреплён в договоре ID пользователя MAX, с которого приходят заявки):
USER_ORG_MAP_PATH = Path(__file__).resolve().parent / "data" / "user_org_map.json" # user_id -> организация (legacy)
USER_CONTEXT_MAP_PATH = Path(__file__).resolve().parent / "data" / "user_context_map.json" # user_id -> {organization, object, address} (и опциональные поля)




# L59–L62: UserSession — хранит (step + draft) для конкретного пользователя.
#
# L65–L140: MaxBotClient — все вызовы MAX API:
# - __init__: создаёт requests.Session и кладёт заголовки (Authorization, Content-Type).
# - get_me: проверка токена (GET /me).
# - get_updates: long polling (GET /updates) + marker пагинация.
# - send_message: POST /messages?user_id=... или chat_id=...
# - answer_callback: POST /answers?callback_id=... (ответ на нажатие кнопки).
#
# L143–L161: генерация inline-клавиатуры:
# - inline_keyboard_rows: формирует attachment типа inline_keyboard.
# - main_menu_keyboard: главное меню (2 кнопки выбора типа + Отмена).
#
# L164–L180: извлечение данных из входящего Message:
# - extract_user_id_from_message: берём sender.user_id, но игнорируем сообщения от бота.
# - recipient_user_id_for_dm: “кому отвечать” в диалоге (фактически user_id отправителя).
# - message_text: безопасно достаёт message.body.text.
#
# L183–L187: append_request_record: атомарно дописывает JSON-строку в data/max_requests.jsonl.
#
# L190–L427: BlastexMaxBot — ядро логики:
# - sessions: in-memory словарь user_id -> UserSession (простая память процесса).
# - handle_user_added: приветствие при событии user_added.
# - handle_message_created: обработка текстовых сообщений (/start, /help, /cancel и шаги формы).
# - handle_message_callback: обработка нажатий кнопок (тип работ/отмена).
# - _finalize_and_notify: финализация — запись заявки на диск + подтверждение пользователю.
# - dispatch: маршрутизация по update_type.
#
# L429–L467: run(): точка входа:
# - берёт токен из MAX_BOT_TOKEN,
# - проверяет /me,
# - запускает бесконечный цикл: get_updates(marker) -> dispatch(update).
#
# Для “боевого” режима (production) обычно переходят на webhook (docs рекомендуют),
# но логика BlastexMaxBot при этом остаётся почти такой же — меняется только способ
# получения update-ов.
# =============================================================================

# настройка логирования: - пишем и в stdout, и в LOG_PATH (удобно для сервера/cron).
logging.basicConfig(
    level=logging.INFO, # уровень логирования (INFO, WARNING, ERROR, DEBUG).
    format="%(asctime)s [%(levelname)s] %(message)s", # формат лога.
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(LOG_PATH, encoding="utf-8")], # handlers — список обработчиков логов.
)
log = logging.getLogger("max_bot") # log — логгер для бота.


class RequestMode(str, Enum):
    UNKNOWN = "unknown"
    DRILL = "drill" # буровые: форма "ЗАЯВКА НА ПРОИЗВОДСТВО БУРОВЫХ РАБОТ"
    BLAST = "blast" # взрывные: форма "ЗАЯВКА НА ПРОИЗВОДСТВО ВЗРЫВНЫХ РАБОТ"


class Step(str, Enum): # Step — перечисление шагов заполнения заявки.
    CHOOSE_TYPE = "choose_type" # CHOOSE_TYPE — выбор типа заявки.
    # Буровые (поля как в согласованной форме; организация/объект обычно фиксированы по user_id)
    D_HORIZON = "d_horizon" # 1) Горизонт
    D_BLOCK = "d_block" # 2) Номер блока
    D_F = "d_f" # 3) f по Протодьяконову
    D_VOLUME = "d_volume" # 5) объём, пог.м
    D_DIAM = "d_diam" # 6) диаметр, мм
    D_BENCH = "d_bench" # 7) высота уступа, м
    D_GRID = "d_grid" # 8) сетка скважин, м
    D_PASSPORT = "d_passport" # 9) паспорт на бурение
    D_READY = "d_ready" # 10) готовность блока
    D_RESP = "d_resp" # 11) ответственный (ФИО, тел)
    D_DEADLINE = "d_deadline" # 12) срок окончания
    # Взрывные
    B_WORK_PERIOD = "b_work_period" # 1) период
    B_PRELIM_VOLUME = "b_prelim_volume" # 2) предварительный объём, м3
    B_MASS_SHOT_DATES = "b_mass_shot_dates" # 3) даты массовых взрывов
    B_F = "b_f" # 4) f по Протодьяконову
    B_MASS_PRJ = "b_mass_prj" # 5) проект МВ
    B_OPENPIT = "b_openpit" # 6) взрывные при ОГР
    B_BENCH = "b_bench" # 7) высота уступа
    B_GRID = "b_grid" # 8) сетка скважин
    IDLE = "idle" # IDLE — состояние ожидания.


@dataclass
class UserContext:
    organization: str
    object_name: str
    object_address: str


@dataclass
class DrillingRequest:
    horizon: Optional[str] = None
    block: Optional[str] = None
    f_protodyakonov: Optional[str] = None
    volume_linear_m: Optional[str] = None
    hole_diam_mm: Optional[str] = None
    bench_height_m: Optional[str] = None
    hole_grid_m: Optional[str] = None
    drilling_passport: Optional[str] = None
    block_ready: Optional[str] = None
    block_ready_responsible: Optional[str] = None
    drilling_end_date: Optional[str] = None


@dataclass
class BlastingRequest:
    work_period: Optional[str] = None
    preliminary_volume_m3: Optional[str] = None
    preliminary_mass_blast_dates: Optional[str] = None
    f_protodyakonov: Optional[str] = None
    mass_blast_project: Optional[str] = None
    open_pit_blasting: Optional[str] = None
    bench_height_m: Optional[str] = None
    hole_grid_m: Optional[str] = None


def _read_json_object_map(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else {}
    except Exception as e:
        log.warning("Не удалось прочитать %s: %s", path, e)
        return {}


def _parse_id_kv_env(raw: str) -> dict[int, str]:
    """Формат: "123=...;456=..."."""
    out: dict[int, str] = {}
    for part in (raw or "").replace("\n", ";").split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        k, v = part.split("=", 1)
        k, v = k.strip(), v.strip()
        if not k or not v:
            continue
        try:
            uid = int(k)
        except Exception:
            continue
        out[uid] = v
    return out


def _parse_id_json_str_map(raw: str) -> dict[int, str]:
    """JSON, где значения — строки: {"123":"..."} ."""
    raw = (raw or "").strip()
    if not raw.startswith("{"):
        return {}
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(obj, dict):
        return {}
    out: dict[int, str] = {}
    for k, v in obj.items():
        try:
            uid = int(k)  # type: ignore[arg-type]
        except Exception:
            continue
        if isinstance(v, str) and v.strip():
            out[uid] = v.strip()
    return out


def _as_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, (int, float, bool)):
        return str(v)
    return ""


def _as_user_context_obj(val: Any) -> Optional[UserContext]:
    if val is None:
        return None
    if isinstance(val, str):
        org = val.strip()
        if not org:
            return None
        return UserContext(organization=org, object_name="", object_address="")
    if not isinstance(val, dict):
        return None
    org = _as_str(val.get("organization") or val.get("org") or val.get("customer"))
    oname = _as_str(val.get("object") or val.get("object_name") or val.get("site") or val.get("title"))
    oaddr = _as_str(val.get("address") or val.get("object_address") or val.get("location"))
    if not org or not (oname or oaddr):
        return None
    if not oname and oaddr:
        oname = oaddr
    return UserContext(organization=org, object_name=oname, object_address=oaddr)


def _merge_str_maps(*maps: dict[int, str]) -> dict[int, str]:
    out: dict[int, str] = {}
    for m in maps:
        for k, v in m.items():
            if v.strip():
                out[k] = v.strip()
    return out


def _merge_user_context_maps(*maps: dict[int, Any]) -> dict[int, Any]:
    out: dict[int, Any] = {}
    for m in maps:
        for k, v in m.items():
            if v is not None:
                out[k] = v
    return out


def _load_user_context_file(path: Path) -> dict[int, Any]:
    obj = _read_json_object_map(path)
    out: dict[int, Any] = {}
    for k, v in obj.items():
        try:
            uid = int(k)  # type: ignore[arg-type]
        except Exception:
            continue
        out[uid] = v
    return out


def resolve_user_context_for_user_id(user_id: int) -> Optional[UserContext]:
    """
    Контрактные данные по user_id:
    - MAX_USER_CONTEXT_MAP (приоритет)
    - data/user_context_map.json
    - legacy: MAX_USER_ORG_MAP + data/user_org_map.json
    """
    env_ctx_raw = os.environ.get("MAX_USER_CONTEXT_MAP", "").strip()
    env_map: dict[int, Any] = {}
    if env_ctx_raw:
        if env_ctx_raw.startswith("{"):
            try:
                obj = json.loads(env_ctx_raw)
            except json.JSONDecodeError:
                obj = {}
            if isinstance(obj, dict):
                for k, v in obj.items():
                    try:
                        env_map[int(k)] = v  # type: ignore[arg-type]
                    except Exception:
                        continue
        else:
            # очень плотный формат неудобен для 3 полей; для простоты: JSON в env, либо файл на диске
            pass

    file_map = _load_user_context_file(USER_CONTEXT_MAP_PATH)
    merged = _merge_user_context_maps(env_map, file_map)
    uctx = _as_user_context_obj(merged.get(user_id))
    if uctx is not None:
        return uctx

    # legacy: только org
    env_org = _merge_str_maps(
        _parse_id_json_str_map(os.environ.get("MAX_USER_ORG_MAP", "")),
        _parse_id_kv_env(os.environ.get("MAX_USER_ORG_MAP", "")),
    )
    file_org = _read_json_object_map(USER_ORG_MAP_PATH)
    legacy: dict[int, str] = {}
    for k, v in file_org.items():
        try:
            uid = int(k)  # type: ignore[arg-type]
        except Exception:
            continue
        if isinstance(v, str) and v.strip():
            legacy[uid] = v.strip()
    merged_org = _merge_str_maps(env_org, legacy)
    s = merged_org.get(user_id, "").strip()
    if s:
        return UserContext(organization=s, object_name="", object_address="")
    return None

@dataclass # DraftRequest — структура “черновика заявки”, которую заполняем по мередиалога.
class DraftRequest:
    work_type: Optional[str] = None  # "Буровые работы" | "Взрывные работы"
    mode: RequestMode = RequestMode.UNKNOWN
    # Контрактный контекст (обычно фиксирован user_id, из договора/справочника)
    user_context: Optional[UserContext] = None
    organization: Optional[str] = None
    object_name: Optional[str] = None
    contact: Optional[str] = None
    address: Optional[str] = None
    # Буровая форма
    drill: DrillingRequest = field(default_factory=DrillingRequest)
    # Взрывная форма
    blast_form: BlastingRequest = field(default_factory=BlastingRequest)
    # (legacy) раньше использовались для “универсальной” взрывной заявки — оставлены, чтобы jsonl-записи оставались читаемыми
    scope: Optional[str] = None
    desired_date: Optional[str] = None
    meta_user: dict[str, Any] = field(default_factory=dict)


class UserSession: # UserSession — хранит (step + draft) для конкретного пользователя.
    def __init__(self) -> None:
        self.step = Step.CHOOSE_TYPE
        self.draft = DraftRequest()


class MaxBotClient:
    def __init__(self, token: str) -> None:
        self._token = token
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": self._token,
                "Content-Type": "application/json",
            }
        )

    def get_me(self) -> dict[str, Any]:
        r = self._session.get(f"{API_BASE}/me", timeout=30)
        r.raise_for_status()
        return r.json()

    def get_updates(
        self,
        marker: Optional[int] = None,
        *,
        timeout: int = 45,
        limit: int = 100,
        types: Optional[list[str]] = None,
    ) -> tuple[list[dict[str, Any]], Optional[int]]:
        params: dict[str, Any] = {"timeout": timeout, "limit": limit}
        if marker is not None:
            params["marker"] = marker
        if types:
            # requests сериализует list как повторяющиеся ключи — для MAX это types=a&types=b
            params["types"] = types
        r = self._session.get(f"{API_BASE}/updates", params=params, timeout=timeout + 10)
        r.raise_for_status()
        data = r.json()
        updates = data.get("updates") or []
        next_marker = data.get("marker")
        return updates, next_marker if next_marker is not None else marker

    def send_message(
        self,
        *,
        user_id: Optional[int] = None,
        chat_id: Optional[int] = None,
        text: str,
        format_: Optional[str] = None,
        attachments: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if user_id is not None:
            params["user_id"] = user_id
        if chat_id is not None:
            params["chat_id"] = chat_id
        body: dict[str, Any] = {"text": text}
        if format_:
            body["format"] = format_
        if attachments:
            body["attachments"] = attachments
        r = self._session.post(f"{API_BASE}/messages", params=params, json=body, timeout=60)
        r.raise_for_status()
        return r.json()

    def answer_callback(
        self,
        callback_id: str,
        *,
        notification: Optional[str] = None,
        message: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        params = {"callback_id": callback_id}
        payload: dict[str, Any] = {}
        if notification is not None:
            payload["notification"] = notification
        if message is not None:
            payload["message"] = message
        r = self._session.post(f"{API_BASE}/answers", params=params, json=payload, timeout=60)
        r.raise_for_status()
        return r.json()


def inline_keyboard_rows(rows: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    return [
        {
            "type": "inline_keyboard",
            "payload": {"buttons": rows},
        }
    ]


def main_menu_keyboard() -> list[dict[str, Any]]:
    return inline_keyboard_rows(
        [
            [
                {"type": "callback", "text": "Буровые работы", "payload": "req_type_drill"},
                {"type": "callback", "text": "Взрывные работы", "payload": "req_type_blast"},
            ],
            [{"type": "callback", "text": "Отмена", "payload": "req_cancel"}],
        ]
    )


def extract_user_id_from_message(message: dict[str, Any]) -> Optional[int]:
    sender = message.get("sender") or {}
    if sender.get("is_bot"):
        return None
    uid = sender.get("user_id")
    return int(uid) if uid is not None else None


def recipient_user_id_for_dm(message: dict[str, Any]) -> Optional[int]:
    """В диалоге для ответа пользователю используем sender.user_id (человек), не бота."""
    return extract_user_id_from_message(message)


def message_text(message: dict[str, Any]) -> str:
    body = message.get("body") or {}
    text = body.get("text") or ""
    return text.strip() if isinstance(text, str) else ""


def append_request_record(record: dict[str, Any]) -> None:
    REQUESTS_JSONL.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with open(REQUESTS_JSONL, "a", encoding="utf-8") as f:
        f.write(line)


class BlastexMaxBot:
    def __init__(self, client: MaxBotClient) -> None:
        self.client = client
        self.sessions: dict[int, UserSession] = {}

    def _session_for(self, user_id: int) -> UserSession:
        if user_id not in self.sessions:
            self.sessions[user_id] = UserSession()
            uctx = resolve_user_context_for_user_id(user_id)
            if uctx:
                d = self.sessions[user_id].draft
                d.user_context = uctx
                d.organization = uctx.organization
                d.object_name = uctx.object_name or None
                d.address = uctx.object_address or None
            self.sessions[user_id].draft.meta_user.setdefault("user_id", user_id)
        return self.sessions[user_id]

    def _reset(self, user_id: int) -> None:
        self.sessions[user_id] = UserSession()
        uctx = resolve_user_context_for_user_id(user_id)
        if uctx:
            d = self.sessions[user_id].draft
            d.user_context = uctx
            d.organization = uctx.organization
            d.object_name = uctx.object_name or None
            d.address = uctx.object_address or None
        self.sessions[user_id].draft.meta_user.setdefault("user_id", user_id)

    @staticmethod
    def _object_header(d: "DraftRequest") -> str:
        oname = (d.object_name or "").strip()
        oaddr = (d.address or "").strip()
        if oname and oaddr and oname != oaddr:
            return f"**Объект:** {oname} ({oaddr})"
        if oname:
            return f"**Объект:** {oname}"
        if oaddr:
            return f"**Адрес объекта:** {oaddr}"
        return "**Объект:** —"

    def _start_after_type_choice(self, *, user_id: int, work: str) -> None:
        sess = self._session_for(user_id)
        d = sess.draft
        d.work_type = work
        d.drill = DrillingRequest()
        d.blast_form = BlastingRequest()
        d.scope = None
        d.desired_date = None
        d.contact = None

        if work == "Буровые работы":
            d.mode = RequestMode.DRILL
            if not d.organization or not d.object_name or not d.address:
                self.client.send_message(
                    user_id=user_id,
                    text=(
                        "Для буровой заявки нужен контрактный профиль user_id: **организация + наименование объекта + адрес/локация**.\n"
                        "Сейчас в справочнике не хватает данных — добавьте запись в `data/user_context_map.json` (или `MAX_USER_CONTEXT_MAP`)."
                    ),
                    format_="markdown",
                )
                sess.step = Step.IDLE
                return

            self.client.send_message(
                user_id=user_id,
                text=(
                    f"**ЗАЯВКА НА ПРОИЗВОДСТВО БУРОВЫХ РАБОТ**\n"
                    f"**Заказчик:** {d.organization}\n"
                    f"{self._object_header(d)}\n\n"
                    "1) Горизонт (как в заявке, одной строкой, например `+482`):"
                ),
                format_="markdown",
            )
            sess.step = Step.D_HORIZON
            return

        # Взрывные: согласованная форма (1–8), а заказчик/объект/адрес фиксируются user_id
        d.mode = RequestMode.BLAST
        if not d.organization or not d.object_name or not d.address:
            self.client.send_message(
                user_id=user_id,
                text=(
                    "Для взрывной заявки нужен контрактный профиль user_id: **организация + наименование объекта + адрес/локация**.\n"
                    "Сейчас в справочнике не хватает данных — добавьте запись в `data/user_context_map.json` (или `MAX_USER_CONTEXT_MAP`)."
                ),
                format_="markdown",
            )
            sess.step = Step.IDLE
            return

        self.client.send_message(
            user_id=user_id,
            text=(
                f"**ЗАЯВКА НА ПРОИЗВОДСТВО ВЗРЫВНЫХ РАБОТ**\n"
                f"**Заказчик:** {d.organization}\n"
                f"{self._object_header(d)}\n\n"
                "1) Период выполнения работ (одной строкой, как в заявке):"
            ),
            format_="markdown",
        )
        sess.step = Step.B_WORK_PERIOD

    def handle_user_added(self, update: dict[str, Any]) -> None:
        user = update.get("user") or {}
        uid = user.get("user_id")
        if uid is None:
            return
        user_id = int(uid)
        self._reset(user_id)
        self.client.send_message(
            user_id=user_id,
            text=(
                "**BlastEX — заявки на работы**\n\n"
                "Здесь можно передать заявку на **буровые** или **взрывные** работы.\n"
                "Нажмите /start чтобы заполнить форму."
            ),
            format_="markdown",
            attachments=main_menu_keyboard(),
        )

    def handle_message_created(self, update: dict[str, Any]) -> None:
        message = update.get("message") or {}
        user_id = recipient_user_id_for_dm(message)
        if user_id is None:
            return

        text = message_text(message)
        if not text:
            self.client.send_message(
                user_id=user_id,
                text="Пожалуйста, отправьте текст или воспользуйтесь кнопками меню.",
            )
            return

        low = text.lower()
        if low in ("/start", "start", "/старт", "старт"):
            self._reset(user_id)
            sess = self._session_for(user_id)
            sess.step = Step.CHOOSE_TYPE
            self.client.send_message(
                user_id=user_id,
                text=(
                    "Выберите тип заявки кнопкой ниже.\n"
                    "Для **буровых работ** бот задаст вопросы по полям стандартной формы (если в договоре привязан ваш `user_id`, "
                    "то заказчик/объект подставятся автоматически).\n"
                    "Для **взрывных работ** — тоже по согласованной форме (1–8), а заказчик/объект фиксируются по `user_id`.\n\n"
                    "Команды: **/cancel** — отменить заполнение."
                ),
                format_="markdown",
                attachments=main_menu_keyboard(),
            )
            return

        if low in ("/help", "help", "/помощь"):
            self.client.send_message(
                user_id=user_id,
                text=(
                    "**Помощь**\n"
                    "/start — новая заявка\n"
                    "/cancel — сбросить черновик\n\n"
                    "Данные сохраняются в файл `data/max_requests.jsonl` на сервере, где запущен бот."
                ),
                format_="markdown",
            )
            return

        if low in ("/cancel", "cancel", "/отмена"):
            self._reset(user_id)
            self.client.send_message(
                user_id=user_id,
                text="Черновик сброшен. Нажмите /start, чтобы начать заново.",
                attachments=main_menu_keyboard(),
            )
            return

        sess = self._session_for(user_id)
        sess.draft.meta_user.setdefault("user_id", user_id)

        if sess.step == Step.CHOOSE_TYPE:
            self.client.send_message(
                user_id=user_id,
                text="Сначала выберите тип работ кнопкой: **Буровые** или **Взрывные**.",
                format_="markdown",
                attachments=main_menu_keyboard(),
            )
            return

        # Буровые: пошагово по форме
        if sess.draft.mode == RequestMode.DRILL:
            dr = sess.draft.drill
            if sess.step == Step.D_HORIZON:
                dr.horizon = text
                sess.step = Step.D_BLOCK
                self.client.send_message(user_id=user_id, text="2) Номер блока:")
                return
            if sess.step == Step.D_BLOCK:
                dr.block = text
                sess.step = Step.D_F
                self.client.send_message(user_id=user_id, text="3) Коэффициент крепости по Протодьяконову (f):")
                return
            if sess.step == Step.D_F:
                dr.f_protodyakonov = text
                sess.step = Step.D_VOLUME
                self.client.send_message(user_id=user_id, text="5) Планируемый объём буровых работ, пог. м:")
                return
            if sess.step == Step.D_VOLUME:
                dr.volume_linear_m = text
                sess.step = Step.D_DIAM
                self.client.send_message(user_id=user_id, text="6) Диаметр скважин, мм:")
                return
            if sess.step == Step.D_DIAM:
                dr.hole_diam_mm = text
                sess.step = Step.D_BENCH
                self.client.send_message(user_id=user_id, text="7) Высота уступа, м (можно диапазон, например 10-14):")
                return
            if sess.step == Step.D_BENCH:
                dr.bench_height_m = text
                sess.step = Step.D_GRID
                self.client.send_message(user_id=user_id, text="8) Сетка скважин, м (например 3,8x3,8):")
                return
            if sess.step == Step.D_GRID:
                dr.hole_grid_m = text
                sess.step = Step.D_PASSPORT
                self.client.send_message(user_id=user_id, text="9) Наличие паспорта на бурение (текстом):")
                return
            if sess.step == Step.D_PASSPORT:
                dr.drilling_passport = text
                sess.step = Step.D_READY
                self.client.send_message(user_id=user_id, text="10) Готовность блока к бурению (текстом):")
                return
            if sess.step == Step.D_READY:
                dr.block_ready = text
                sess.step = Step.D_RESP
                self.client.send_message(
                    user_id=user_id,
                    text="11) Ответственный за готовность блока (ФИО и телефон одной строкой):",
                )
                return
            if sess.step == Step.D_RESP:
                dr.block_ready_responsible = text
                sess.step = Step.D_DEADLINE
                self.client.send_message(user_id=user_id, text="12) Срок окончания буровых работ (как в заявке, одной строкой):")
                return
            if sess.step == Step.D_DEADLINE:
                dr.drilling_end_date = text
                self._finalize_and_notify(user_id, sess)
                return

        # Взрывные: форма 1–8 (договорной контекст user_id: заказчик/объект/адрес)
        if sess.draft.mode == RequestMode.BLAST:
            bl = sess.draft.blast_form
            if sess.step == Step.B_WORK_PERIOD:
                bl.work_period = text
                sess.step = Step.B_PRELIM_VOLUME
                self.client.send_message(user_id=user_id, text="2) Предварительный объём работ, м³ (одной строкой):")
                return
            if sess.step == Step.B_PRELIM_VOLUME:
                bl.preliminary_volume_m3 = text
                sess.step = Step.B_MASS_SHOT_DATES
                self.client.send_message(
                    user_id=user_id,
                    text="3) Предварительные даты производства массовых взрывов (одной строкой):",
                )
                return
            if sess.step == Step.B_MASS_SHOT_DATES:
                bl.preliminary_mass_blast_dates = text
                sess.step = Step.B_F
                self.client.send_message(user_id=user_id, text="4) Коэффициент крепости по Протодьяконову (f):")
                return
            if sess.step == Step.B_F:
                bl.f_protodyakonov = text
                sess.step = Step.B_MASS_PRJ
                self.client.send_message(
                    user_id=user_id,
                    text="5) Разработку и согласование проекта массового взрыва (текстом, например “не требуется”):",
                )
                return
            if sess.step == Step.B_MASS_PRJ:
                bl.mass_blast_project = text
                sess.step = Step.B_OPENPIT
                self.client.send_message(
                    user_id=user_id,
                    text="6) Производство взрывных работ при ведении открытых горных работ (текстом, например “не требуется”):",
                )
                return
            if sess.step == Step.B_OPENPIT:
                bl.open_pit_blasting = text
                sess.step = Step.B_BENCH
                self.client.send_message(
                    user_id=user_id,
                    text="7) Высота уступа, м (можно диапазон, например 10-14):",
                )
                return
            if sess.step == Step.B_BENCH:
                bl.bench_height_m = text
                sess.step = Step.B_GRID
                self.client.send_message(
                    user_id=user_id,
                    text="8) Сетка скважин, м (текстом, например “определить проектом”):",
                )
                return
            if sess.step == Step.B_GRID:
                bl.hole_grid_m = text
                self._finalize_and_notify(user_id, sess)
                return

        # IDLE: напоминание
        self.client.send_message(
            user_id=user_id,
            text="Нажмите /start, чтобы оформить новую заявку.",
            attachments=main_menu_keyboard(),
        )

    def handle_message_callback(self, update: dict[str, Any]) -> None:
        cb = update.get("callback") or {}
        callback_id = cb.get("callback_id")
        payload = (cb.get("payload") or "").strip()
        user = cb.get("user") or {}
        uid = user.get("user_id")
        if not callback_id or uid is None:
            log.warning("message_callback без callback_id или user: %s", update)
            return
        user_id = int(uid)

        if payload == "req_cancel":
            try:
                self.client.answer_callback(str(callback_id), notification="Отменено")
            except requests.RequestException as e:
                log.warning("answer_callback: %s", e)
            self._reset(user_id)
            self.client.send_message(user_id=user_id, text="Заявка отменена. /start — сначала.", attachments=main_menu_keyboard())
            return

        if payload == "req_type_drill":
            work = "Буровые работы"
        elif payload == "req_type_blast":
            work = "Взрывные работы"
        else:
            try:
                self.client.answer_callback(str(callback_id), notification="Неизвестная кнопка")
            except requests.RequestException:
                pass
            return

        try:
            self.client.answer_callback(str(callback_id), notification="Тип заявки выбран")
        except requests.RequestException as e:
            log.warning("answer_callback: %s", e)

        sess = self._session_for(user_id)
        base = dict(sess.draft.meta_user or {})
        base.update(
            {
                "user_id": user_id,
                "first_name": user.get("first_name"),
                "last_name": user.get("last_name"),
                "name": user.get("name"),
            }
        )
        sess.draft.meta_user = base
        self._start_after_type_choice(user_id=user_id, work=work)

    def _finalize_and_notify(self, user_id: int, sess: UserSession) -> None:
        d = sess.draft
        now = datetime.now(timezone.utc).isoformat()
        record: dict[str, Any] = {
            "received_at_utc": now,
            "work_type": d.work_type,
            "mode": d.mode.value,
            "organization": d.organization,
            "object_name": d.object_name,
            "object_address": d.address,
            "contact": d.contact,
            "scope": d.scope,
            "desired_date": d.desired_date,
            "drill": d.drill.__dict__ if d.mode == RequestMode.DRILL else None,
            "blast": d.blast_form.__dict__ if d.mode == RequestMode.BLAST else None,
            "user": d.meta_user,
        }
        if d.user_context is not None:
            record["user_context"] = {
                "organization": d.user_context.organization,
                "object_name": d.user_context.object_name,
                "object_address": d.user_context.object_address,
            }
        try:
            append_request_record(record)
        except OSError as e:
            log.error("Не удалось записать заявку: %s", e)
            self.client.send_message(
                user_id=user_id,
                text="Ошибка записи заявки на сервере. Попробуйте позже или свяжитесь с администратором.",
            )
            return

        if d.mode == RequestMode.DRILL:
            dr = d.drill
            summary = (
                "**Заявка принята (буровые работы)**\n\n"
                f"{self._object_header(d)}\n"
                f"**Заказчик:** {d.organization}\n"
                f"1) **Горизонт:** {dr.horizon}\n"
                f"2) **Блок:** {dr.block}\n"
                f"3) **f (Протодьяконов):** {dr.f_protodyakonov}\n"
                f"5) **Объём, пог.м:** {dr.volume_linear_m}\n"
                f"6) **Ø, мм:** {dr.hole_diam_mm}\n"
                f"7) **Уступ, м:** {dr.bench_height_m}\n"
                f"8) **Сетка, м:** {dr.hole_grid_m}\n"
                f"9) **Паспорт:** {dr.drilling_passport}\n"
                f"10) **Готовность:** {dr.block_ready}\n"
                f"11) **Ответственный:** {dr.block_ready_responsible}\n"
                f"12) **Срок окончания:** {dr.drilling_end_date}\n\n"
                "Новая заявка: /start"
            )
        elif d.mode == RequestMode.BLAST:
            b = d.blast_form
            summary = (
                "**Заявка принята (взрывные работы)**\n\n"
                f"{self._object_header(d)}\n"
                f"**Заказчик:** {d.organization}\n"
                f"1) **Период:** {b.work_period}\n"
                f"2) **Объём, м³:** {b.preliminary_volume_m3}\n"
                f"3) **Даты МВ:** {b.preliminary_mass_blast_dates}\n"
                f"4) **f (Протодьяконов):** {b.f_protodyakonov}\n"
                f"5) **Проект МВ:** {b.mass_blast_project}\n"
                f"6) **ОГР:** {b.open_pit_blasting}\n"
                f"7) **Уступ, м:** {b.bench_height_m}\n"
                f"8) **Сетка, м:** {b.hole_grid_m}\n\n"
                "Новая заявка: /start"
            )
        else:
            summary = (
                "**Заявка принята**\n\n"
                f"**Тип:** {d.work_type}\n"
                f"**Заказчик:** {d.organization}\n"
                f"**Контакт:** {d.contact}\n"
                f"{self._object_header(d)}\n"
                f"**Работы:** {d.scope}\n"
                f"**Сроки:** {d.desired_date}\n\n"
                "Мы передадим данные исполнителю услуги. Новая заявка: /start"
            )
        sess.step = Step.IDLE
        self.client.send_message(user_id=user_id, text=summary, format_="markdown", attachments=main_menu_keyboard())

    def dispatch(self, update: dict[str, Any]) -> None:
        ut = update.get("update_type")
        if ut == "message_created":
            self.handle_message_created(update)
        elif ut == "message_callback":
            self.handle_message_callback(update)
        elif ut == "user_added":
            self.handle_user_added(update)
        else:
            log.debug("Пропуск update_type=%s", ut)


def run() -> None:
    token = os.environ.get("MAX_BOT_TOKEN", "").strip()
    if not token:
        log.error("Задайте переменную окружения MAX_BOT_TOKEN (токен из business.max.ru → Чат-боты → Интеграция).")
        sys.exit(1)

    client = MaxBotClient(token)
    try:
        me = client.get_me()
        log.info("Бот подключён: %s (@%s)", me.get("first_name") or me.get("name"), me.get("username"))
    except requests.RequestException as e:
        log.error("Не удалось вызвать /me — проверьте токен и сеть: %s", e)
        sys.exit(1)

    bot = BlastexMaxBot(client)
    marker: Optional[int] = None
    types = ["message_created", "message_callback", "user_added"]

    log.info("Long polling запущен (GET /updates). Остановка: Ctrl+C.")

    while True:
        try:
            updates, marker = client.get_updates(marker, timeout=45, types=types)
        except requests.RequestException as e:
            log.warning("Ошибка polling: %s — повтор через 3 с", e)
            time.sleep(3)
            continue

        for upd in updates:
            try:
                bot.dispatch(upd)
            except requests.RequestException as e:
                log.exception("Ошибка API при обработке update: %s", e)
            except Exception:
                log.exception("Необработанное исключение при update")


if __name__ == "__main__":
    run()
