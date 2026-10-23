"""Фоновый подбор раскладки: реестр задач в памяти процесса API и хранение итога.

Прод запускает один процесс uvicorn, поэтому реестр в памяти общий для всех
запросов. На весь сервер одновременно идёт не больше одного подбора: бюджет
перебора рассчитан на одно ядро. Сам перебор идёт в дочернем процессе
(контекст `spawn`): чистый Python держит GIL, и в потоке подбор тормозил бы
остальные запросы. Ход выполнения и итог приходят через очередь, остановка —
через событие. Поток-наблюдатель в родителе читает очередь, обновляет реестр
и пишет итог в `designs/layout_search/{design_id}.json` рядом с паспортами — так он
переживает перезапуск сервера. Идущий подбор перезапуск не переживает:
новый реестр о нём не знает и показывает сохранённый итог или `idle`.

Подбор запускается только для сохранённого паспорта организации; если паспорт
удалили, пока шёл подбор, итог не пишется (запись в журнал).

Ошибка перебора, выход дочернего процесса без итога и превышение
`budget_s + grace_s` дают статус `failed` без итога и отпечатка: карточки
прошлого итога не показываются, хотя файл не переписывается. Ошибка
забывается при следующем запуске или остановке. Исключение перебора
пользователю не показывается (общий `ERROR_TEXT`), подробности — в журнале
сервера. Испорченный или
несовместимый файл итога читается как «нет итога» (`idle`) с записью в журнал.
"""
from __future__ import annotations

import json
import logging
import multiprocessing
import os
import queue as queue_module
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from design.layout_search.evaluate import SearchContext
from design.layout_search.search import search_layout
from design.layout_search.serialize import result_to_dict
from design.lifecycle import utc_now_iso
from design.models import BlastDesign
from design.persistence import DesignNotFoundError, design_path, layout_search_path

logger = logging.getLogger(__name__)

STATE_IDLE = "idle"
STATE_RUNNING = "running"
STATE_DONE = "done"
STATE_STOPPED = "stopped"
STATE_FAILED = "failed"

BUSY_MESSAGE = "Подбор раскладки уже идёт: блок «{name}». Дождитесь окончания или остановите его."
# Подбор блока другой команды (организации): имя её блока не раскрывается.
BUSY_OTHER_MESSAGE = "Сервер занят подбором раскладки другого блока. Попробуйте позже."
ERROR_PREFIX = "Подбор раскладки завершился с ошибкой: "
# Исключение перебора: служебные имена пользователю не показываются.
ERROR_TEXT = "Подбор раскладки завершился с ошибкой. Подробности — в журнале сервера."
NOT_SAVED_MESSAGE = "Паспорт не найден — сохраните его перед подбором."
NO_RESULT_TEXT = "процесс подбора завершился без результата."
TIMEOUT_TEXT = "подбор не уложился в {seconds:.0f} с и прерван."

RUNNER_PROCESS = "process"
RUNNER_THREAD = "thread"
# Период опроса очереди наблюдателем, с.
_POLL_S = 0.2
# Сколько ждать остаток очереди и завершение дочернего процесса, с.
_DRAIN_S = 1.0
_JOIN_S = 5.0

SearchFn = Callable[..., Any]


class LayoutSearchBusyError(Exception):
    """Подбор уже идёт (этого или другого блока): второй запуск не принимается."""


def run_search_child(
    inputs: dict[str, Any],
    relief_min_ms_m: float,
    relief_max_ms_m: float | None,
    budget_s: float,
    out: Any,
    stop: Any,
    search_fn: SearchFn = search_layout,
) -> None:
    """Тело дочернего процесса (модульная функция — для `spawn`).

    Восстанавливает паспорт, строит контекст с границами темпа и запускает
    перебор. В очередь `out` уходят `("progress", этап, сделано, всего)`, затем
    `("result", словарь итога)` или `("error", текст)`. Остановка — `stop.is_set()`.
    """
    try:
        design = BlastDesign.from_dict(inputs)
        ctx = SearchContext.from_design(
            design, relief_min_ms_m=relief_min_ms_m, relief_max_ms_m=relief_max_ms_m
        )
        result = search_fn(
            ctx,
            budget_s=budget_s,
            progress=lambda stage, done, total: out.put(("progress", stage, done, total)),
            should_stop=stop.is_set,
        )
        out.put(("result", result_to_dict(result)))
    except Exception:  # noqa: BLE001 — любая ошибка перебора → статус «ошибка»
        # Подробности — только в журнал: текст исключения несёт служебные имена.
        logger.exception("Подбор раскладки завершился с ошибкой")
        out.put(("error", ERROR_TEXT))


@dataclass
class _Job:
    team_id: str
    design_id: str
    design_name: str
    fingerprint: str
    warnings: list[str]
    started: float
    queue: Any = None
    stop_event: Any = None
    worker: Any = None
    stage: str | None = None
    done: int = 0
    total: int = 0

    @property
    def key(self) -> tuple[str, str]:
        return (self.team_id, self.design_id)


def _read_stored(path: Path) -> dict[str, Any] | None:
    """Сохранённый итог подбора; нет файла — None, испорченный — None с записью в журнал."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError:
        logger.warning("Файл итога подбора раскладки не прочитан: %s", path, exc_info=True)
        return None
    try:
        data = json.loads(text)
    except ValueError:
        logger.warning("Файл итога подбора раскладки испорчен: %s", path)
        return None
    if not _stored_shape_ok(data):
        logger.warning("Файл итога подбора раскладки несовместим: %s", path)
        return None
    return data


def _stored_shape_ok(data: Any) -> bool:
    """Верхний уровень файла итога: объект, состояние done/stopped, итог — объект."""
    if not isinstance(data, dict):
        return False
    fingerprint = data.get("fingerprint")
    if fingerprint is not None and not isinstance(fingerprint, str):
        return False
    if data.get("state", STATE_DONE) not in (STATE_DONE, STATE_STOPPED):
        return False
    result = data.get("result")
    return result is None or isinstance(result, dict)


def _write_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Запись через временный файл: читатель не увидит недописанный JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


class LayoutSearchJobs:
    """Реестр подборов раскладки: не больше одного идущего подбора на сервер."""

    def __init__(
        self,
        *,
        runner: str = RUNNER_PROCESS,
        budget_s: float = 150.0,
        grace_s: float = 60.0,
        search_fn: SearchFn = search_layout,
    ) -> None:
        """`runner="thread"` — только для тестов; `search_fn` для процесса — модульная функция."""
        if runner not in (RUNNER_PROCESS, RUNNER_THREAD):
            raise ValueError(f"Неизвестный способ запуска подбора: {runner}")
        self._runner = runner
        self._budget_s = float(budget_s)
        self._grace_s = float(grace_s)
        self._search_fn = search_fn
        self._lock = threading.Lock()
        self._active: _Job | None = None
        # Ошибки последних подборов по блокам (в файл не пишутся): текст и время запуска, с.
        self._failed: dict[tuple[str, str], tuple[str, float]] = {}

    # --- запуск -------------------------------------------------------------

    def start(
        self,
        team_id: str,
        design_id: str,
        design_name: str,
        inputs: dict[str, Any],
        fingerprint: str,
        relief_min_ms_m: float,
        relief_max_ms_m: float | None,
        warnings: list[str],
    ) -> None:
        """Запускает подбор блока; при идущем подборе — `LayoutSearchBusyError`."""
        layout_search_path(team_id, design_id)  # проверка design_id до занятия слота
        # Итог пишется рядом с паспортом организации: без паспорта — не запускаем.
        if not design_path(team_id, design_id).exists():
            raise DesignNotFoundError(NOT_SAVED_MESSAGE)
        job = _Job(
            team_id=team_id,
            design_id=design_id,
            design_name=design_name,
            fingerprint=fingerprint,
            warnings=list(warnings),
            started=time.monotonic(),
        )
        spawn = multiprocessing.get_context("spawn")
        with self._lock:
            if self._active is not None:
                if self._active.team_id == team_id:
                    raise LayoutSearchBusyError(BUSY_MESSAGE.format(name=self._active.design_name))
                raise LayoutSearchBusyError(BUSY_OTHER_MESSAGE)
            # Очередь и событие — после проверки занятости (отказ их не создаёт) и
            # до освобождения блокировки (`stop` сразу после старта их видит).
            if self._runner == RUNNER_PROCESS:
                job.queue, job.stop_event = spawn.Queue(), spawn.Event()
            else:
                job.queue, job.stop_event = queue_module.Queue(), threading.Event()
            self._active = job
            self._failed.pop(job.key, None)

        args = (inputs, relief_min_ms_m, relief_max_ms_m, self._budget_s, job.queue, job.stop_event, self._search_fn)
        try:
            if self._runner == RUNNER_PROCESS:
                job.worker = spawn.Process(target=run_search_child, args=args, daemon=True, name="layout-search")
            else:
                job.worker = threading.Thread(target=run_search_child, args=args, daemon=True, name="layout-search")
            job.worker.start()
        except BaseException:
            with self._lock:
                self._active = None
            raise
        try:
            threading.Thread(target=self._watch, args=(job,), daemon=True, name="layout-search-watch").start()
        except BaseException:
            # Без наблюдателя ребёнок остался бы без присмотра, а слот — занятым.
            try:
                self._kill(job)
            finally:
                with self._lock:
                    self._active = None
            raise

    # --- статус и остановка -------------------------------------------------

    def status(self, team_id: str, design_id: str) -> dict[str, Any]:
        """Состояние подбора блока: `running` — из реестра, иначе — из файла."""
        path = layout_search_path(team_id, design_id)
        with self._lock:
            job = self._active
            if job is not None and job.key == (team_id, design_id):
                return {
                    "state": STATE_RUNNING,
                    "stage": job.stage,
                    "done": job.done,
                    "total": job.total,
                    "elapsed_s": round(time.monotonic() - job.started, 1),
                    "fingerprint": job.fingerprint,
                    "result": None,
                    "error": None,
                }
            failed = self._failed.get((team_id, design_id))
        if failed is not None:
            # Карточки прошлого итога при ошибке не показываются (файл не тронут);
            # время — упавшего запуска.
            error, elapsed_s = failed
            return {
                "state": STATE_FAILED,
                "stage": None,
                "done": 0,
                "total": 0,
                "elapsed_s": elapsed_s,
                "fingerprint": None,
                "result": None,
                "error": error,
            }
        stored = _read_stored(path)
        result = stored.get("result") if stored else None
        state = str(stored.get("state") or STATE_DONE) if stored is not None else STATE_IDLE
        return {
            "state": state,
            "stage": None,
            "done": 0,
            "total": 0,
            "elapsed_s": result.get("elapsed_s") if isinstance(result, dict) else None,
            "fingerprint": stored.get("fingerprint") if stored else None,
            "result": result,
            "error": None,
        }

    def stop(self, team_id: str, design_id: str) -> bool:
        """Просит идущий подбор блока остановиться; False — подбор этого блока не идёт.

        Ошибка прошлого подбора блока при этом забывается.
        """
        with self._lock:
            self._failed.pop((team_id, design_id), None)
            job = self._active
            if job is None or job.key != (team_id, design_id):
                return False
            job.stop_event.set()
            return True

    # --- наблюдатель --------------------------------------------------------

    def _alive(self, job: _Job) -> bool:
        return bool(job.worker is not None and job.worker.is_alive())

    def _handle(self, job: _Job, message: tuple) -> tuple[str, Any] | None:
        """Сообщение ребёнка: ход выполнения — в реестр; итог или ошибка — наружу."""
        kind = message[0]
        if kind == "progress":
            _, stage, done, total = message
            with self._lock:
                job.stage, job.done, job.total = stage, int(done), int(total)
            return None
        if kind in ("result", "error"):
            return kind, message[1]
        return None

    def _drain(self, job: _Job) -> tuple[str, Any] | None:
        """Дочитывает очередь после выхода ребёнка."""
        while True:
            try:
                message = job.queue.get(timeout=_DRAIN_S)
            except queue_module.Empty:
                return None
            outcome = self._handle(job, message)
            if outcome is not None:
                return outcome

    def _kill(self, job: _Job) -> None:
        job.stop_event.set()
        if self._runner == RUNNER_PROCESS and job.worker is not None:
            job.worker.terminate()
            job.worker.join(_JOIN_S)
            if job.worker.is_alive():
                job.worker.kill()
                job.worker.join(_JOIN_S)
        # Поток убить нельзя: событие остановки просит его закончить, он демон.

    def _wait_outcome(self, job: _Job) -> tuple[str, Any]:
        deadline = job.started + self._budget_s + self._grace_s
        while True:
            # Срок проверяется на каждом шаге: ребёнок, шлющий ход без перерыва,
            # иначе не дал бы очереди опустеть и пережил бы сторожа.
            if time.monotonic() >= deadline:
                self._kill(job)
                return "error", TIMEOUT_TEXT.format(seconds=self._budget_s + self._grace_s)
            try:
                message = job.queue.get(timeout=_POLL_S)
            except queue_module.Empty:
                if not self._alive(job):
                    return self._drain(job) or ("error", NO_RESULT_TEXT)
                continue
            outcome = self._handle(job, message)
            if outcome is not None:
                return outcome

    def _watch(self, job: _Job) -> None:
        """Ждёт итог ребёнка, пишет файл и освобождает слот."""
        error: str | None = None
        try:
            kind, payload = self._wait_outcome(job)
            if kind == "result":
                self._store(job, payload)
            else:
                error = str(payload)
        except Exception:  # noqa: BLE001 — слот освобождается при любой ошибке
            logger.exception("Наблюдатель подбора раскладки упал")
            error = ERROR_TEXT
        finally:
            try:
                self._finish_worker(job)
            except Exception:  # noqa: BLE001 — сбой уборки не держит слот
                logger.exception("Не удалось завершить процесс подбора раскладки")
            finally:
                elapsed_s = round(time.monotonic() - job.started, 1)
                with self._lock:
                    if error is not None:
                        text = error if error == ERROR_TEXT else ERROR_PREFIX + error
                        self._failed[job.key] = (text, elapsed_s)
                    else:
                        self._failed.pop(job.key, None)
                    self._active = None

    def _store(self, job: _Job, result: dict[str, Any]) -> None:
        """Пишет итог: предупреждения запуска (порода) идут первыми."""
        warnings = list(job.warnings)
        for text in result.get("warnings", []):
            if text not in warnings:
                warnings.append(text)
        result = {**result, "warnings": warnings}
        if not design_path(job.team_id, job.design_id).exists():
            logger.warning(
                "Паспорт %s удалён во время подбора раскладки — итог не записан", job.design_id
            )
            return
        payload = {
            "fingerprint": job.fingerprint,
            # `stopped` — перебор прерван по просьбе пользователя; исчерпанный
            # бюджет — `done` с пометкой `stopped_early` в итоге.
            "state": STATE_STOPPED if job.stop_event.is_set() and result.get("stopped_early") else STATE_DONE,
            "finished_at": utc_now_iso(),
            "result": result,
        }
        _write_atomic(layout_search_path(job.team_id, job.design_id), payload)

    def _finish_worker(self, job: _Job) -> None:
        if self._runner != RUNNER_PROCESS or job.worker is None:
            return
        job.worker.join(_JOIN_S)
        if job.worker.is_alive():
            self._kill(job)
        job.queue.close()


_instance: LayoutSearchJobs | None = None
_instance_lock = threading.Lock()


def get_layout_search_jobs() -> LayoutSearchJobs:
    """Один реестр на процесс API (для `Depends` и подмены в тестах)."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = LayoutSearchJobs()
        return _instance
