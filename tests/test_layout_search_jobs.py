"""Фоновые задачи подбора раскладки: реестр, остановка, ошибки и хранение."""
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from design.geometry import crest_azimuth_deg
from design.layout_search import jobs as jobs_module
from design.layout_search.jobs import LayoutSearchBusyError, LayoutSearchJobs
from design.layout_search.search import NOTHING_EVALUATED
from design.models import BlastDesign
from design.persistence import DesignNotFoundError, delete_design, design_path, layout_search_path, list_designs, save_design
from tests.front_rows_fixtures import _rect_contour

TEAM = "t"
WAIT_S = 120.0


def _inputs(width=40.0, height=30.0, name="Блок 1", design_id="d1") -> dict:
    contour = _rect_contour(width, height, face_angle_deg=75.0)
    params = {
        "pattern": "rectangular",
        "spacing_a_m": 4.0,
        "burden_b_m": 4.0,
        "row_azimuth_deg": crest_azimuth_deg(contour),
        "offset_from_face_m": 1.0,
        "edge_margin_m": 1.0,
        "subdrill_m": 1.0,
    }
    return BlastDesign(design_id=design_id, name=name, contour=contour, pattern_params=params).to_dict()


def failing_search(ctx, **kwargs):
    """Подменённый поиск: падает сразу (модульная — годится и для `spawn`)."""
    raise RuntimeError("сломался перебор")


def chatty_search(ctx, *, progress=None, **kwargs):
    """Подменённый поиск: не слушает ни бюджет, ни остановку и всё время шлёт ход."""
    deadline = time.monotonic() + 60.0
    done = 0
    while time.monotonic() < deadline:
        done += 1
        progress("geometry", done, 10**9)
        time.sleep(0.01)
    raise RuntimeError("сторож не сработал")


def _start(jobs, design_id="d1", name="Блок 1", fingerprint="fp1", inputs=None, warnings=None, team=TEAM):
    jobs.start(
        team, design_id, name, inputs or _inputs(name=name, design_id=design_id), fingerprint,
        3.0, None, list(warnings or []),
    )


def _wait(jobs, design_id="d1", timeout=WAIT_S) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = jobs.status(TEAM, design_id)
        if status["state"] != "running":
            return status
        time.sleep(0.05)
    raise AssertionError("подбор не закончился вовремя")


class LayoutSearchJobsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)
        self.jobs = LayoutSearchJobs(runner="thread", budget_s=20.0)
        # Тест не оставляет за собой идущий подбор.
        self.addCleanup(self._drain, self.jobs)

    def _drain(self, jobs):
        for design_id in ("d1", "d2"):
            jobs.stop(TEAM, design_id)
        for design_id in ("d1", "d2"):
            _wait(jobs, design_id)

    def test_start_status_done(self):
        _start(self.jobs, warnings=["Порода не найдена."])
        stage = None
        deadline = time.monotonic() + WAIT_S
        while time.monotonic() < deadline:
            status = self.jobs.status(TEAM, "d1")
            if status["state"] != "running":
                break
            self.assertIsNone(status["result"])
            self.assertEqual(status["fingerprint"], "fp1")
            if status["stage"]:
                stage = status["stage"]
                self.assertIn(stage, ("geometry", "front_rows", "refine"))
                self.assertLessEqual(status["done"], status["total"])
            time.sleep(0.02)
        self.assertIsNotNone(stage)

        status = _wait(self.jobs)
        self.assertEqual(status["state"], "done")
        self.assertEqual(status["fingerprint"], "fp1")
        result = status["result"]
        self.assertTrue(1 <= len(result["best"]) <= 3)
        for item in result["best"]:
            self.assertTrue(item["holes"])
            self.assertIn("connectors", item["network"])
            self.assertIn(item["cut_flank"], ("left", "right"))
            self.assertIn("spacing_a_m", item["params"])
        self.assertEqual(result["warnings"][0], "Порода не найдена.")

        stored = json.loads(layout_search_path(TEAM, "d1").read_text(encoding="utf-8"))
        self.assertEqual(stored["state"], "done")
        self.assertEqual(stored["fingerprint"], "fp1")
        self.assertTrue(stored["finished_at"])
        self.assertEqual(stored["result"], result)

    def test_busy_same_and_other_block(self):
        _start(self.jobs, name="Блок 66")
        for design_id in ("d1", "d2"):
            with self.subTest(design_id=design_id):
                with self.assertRaises(LayoutSearchBusyError) as caught:
                    _start(self.jobs, design_id=design_id, name="Другой")
                self.assertIn("«Блок 66»", str(caught.exception))
        self.assertEqual(self.jobs.status(TEAM, "d2")["state"], "idle")

    def test_busy_other_team_hides_block_name(self):
        _start(self.jobs, name="Блок 66")
        with self.assertRaises(LayoutSearchBusyError) as caught:
            _start(self.jobs, design_id="d2", name="Другой", team="other")
        self.assertNotIn("Блок 66", str(caught.exception))
        self.assertEqual(str(caught.exception), jobs_module.BUSY_OTHER_MESSAGE)

    def test_stop(self):
        _start(self.jobs)
        self.assertTrue(self.jobs.stop(TEAM, "d1"))
        self.assertFalse(self.jobs.stop(TEAM, "d2"))
        status = _wait(self.jobs)
        self.assertEqual(status["state"], "stopped")
        result = status["result"]
        self.assertTrue(result["stopped_early"])
        self.assertTrue(result["best"] or NOTHING_EVALUATED in result["warnings"])
        self.assertTrue(layout_search_path(TEAM, "d1").exists())
        self.assertFalse(self.jobs.stop(TEAM, "d1"))

    def test_child_failure(self):
        layout_search_path(TEAM, "d1").parent.mkdir(parents=True, exist_ok=True)
        previous = {"fingerprint": "old", "state": "done", "finished_at": "x", "result": {"best": []}}
        layout_search_path(TEAM, "d1").write_text(json.dumps(previous), encoding="utf-8")

        jobs = LayoutSearchJobs(runner="thread", budget_s=20.0, search_fn=failing_search)
        _start(jobs)
        status = _wait(jobs)
        self.assertEqual(status["state"], "failed")
        self.assertIn("Подбор раскладки завершился с ошибкой: сломался перебор", status["error"])
        # Файл не переписан: прежний результат остаётся.
        self.assertEqual(status["result"], previous["result"])
        self.assertEqual(status["fingerprint"], "old")
        # Время — упавшего запуска, а не прежнего итога.
        self.assertIsInstance(status["elapsed_s"], float)
        # Слот свободен: следующий запуск возможен.
        _start(jobs, design_id="d2")
        self.assertEqual(_wait(jobs, "d2")["state"], "failed")

    def test_restart_forgets_running(self):
        _start(self.jobs)
        fresh = LayoutSearchJobs(runner="thread", budget_s=20.0)
        self.assertEqual(fresh.status(TEAM, "d1")["state"], "idle")
        self.assertIsNone(fresh.status(TEAM, "d1")["result"])

        self.jobs.stop(TEAM, "d1")
        _wait(self.jobs)
        restarted = LayoutSearchJobs(runner="thread", budget_s=20.0)
        status = restarted.status(TEAM, "d1")
        self.assertEqual(status["state"], "stopped")
        self.assertEqual(status["fingerprint"], "fp1")
        self.assertIsNotNone(status["result"])

    def test_watchdog_terminates(self):
        jobs = LayoutSearchJobs(runner="thread", budget_s=0.5, grace_s=0.0, search_fn=_slow_search)
        _start(jobs)
        worker = jobs._active.worker
        status = _wait(jobs)
        self.assertEqual(status["state"], "failed")
        self.assertIn("Подбор раскладки завершился с ошибкой", status["error"])
        # Поток не убить: сторож ставит событие остановки, поток доходит до конца сам.
        worker.join(10.0)
        self.assertFalse(worker.is_alive())

    def test_path_rejects_traversal(self):
        for bad in ("../x", "", ".", ".."):
            with self.subTest(bad=bad):
                with self.assertRaises(DesignNotFoundError):
                    layout_search_path(TEAM, bad)
        path = layout_search_path(TEAM, "abc")
        self.assertEqual((path.parent.name, path.name), ("layout_search", "abc.json"))

    def test_search_file_does_not_collide_with_design(self):
        # Паспорт с id «x.layout_search» и итог подбора блока «x» — разные файлы.
        save_design(TEAM, BlastDesign.from_dict(_inputs(design_id="x")))
        save_design(TEAM, BlastDesign.from_dict(_inputs(design_id="x.layout_search")))
        self.assertNotEqual(layout_search_path(TEAM, "x"), design_path(TEAM, "x.layout_search"))
        layout_search_path(TEAM, "x").parent.mkdir(parents=True, exist_ok=True)
        layout_search_path(TEAM, "x").write_text("{}", encoding="utf-8")
        self.assertEqual(sorted(s.design_id for s in list_designs(TEAM)), ["x", "x.layout_search"])
        # Удаление паспорта убирает и его итог подбора, чужой итог не трогает.
        layout_search_path(TEAM, "x.layout_search").write_text("{}", encoding="utf-8")
        delete_design(TEAM, "x")
        self.assertFalse(layout_search_path(TEAM, "x").exists())
        self.assertTrue(layout_search_path(TEAM, "x.layout_search").exists())
        self.assertTrue(design_path(TEAM, "x.layout_search").exists())

    def test_process_runner_done(self):
        jobs = LayoutSearchJobs(runner="process", budget_s=20.0)
        self.addCleanup(self._drain, jobs)
        jobs.start(TEAM, "d1", "Блок 1", _inputs(16.0, 12.0), "fp", 3.0, None, [])
        status = _wait(jobs)
        self.assertEqual(status["state"], "done", status.get("error"))
        self.assertTrue(status["result"]["best"])
        self.assertTrue(status["result"]["best"][0]["holes"])

    def test_process_watchdog_kills_chatty_child(self):
        # Ребёнок шлёт ход без перерыва и бюджет не слушает: сторож всё равно убивает его.
        jobs = LayoutSearchJobs(runner="process", budget_s=3.0, grace_s=0.0, search_fn=chatty_search)
        _start(jobs)
        worker = jobs._active.worker
        status = _wait(jobs, timeout=60.0)
        self.assertEqual(status["state"], "failed")
        self.assertIn("не уложился", status["error"])
        self.assertIsNone(jobs._active)
        self.assertFalse(worker.is_alive())
        self.assertIsNotNone(worker.exitcode)  # процесс пожат, не зомби
        self.assertFalse(layout_search_path(TEAM, "d1").exists())

    def test_singleton(self):
        self.assertIs(jobs_module.get_layout_search_jobs(), jobs_module.get_layout_search_jobs())


def _slow_search(ctx, *, should_stop=None, **kwargs):
    """Поиск, не слушающий бюджет: держит слот, пока его не остановят."""
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline and not (should_stop and should_stop()):
        time.sleep(0.01)
    raise RuntimeError("остановлен")


if __name__ == "__main__":
    unittest.main()
