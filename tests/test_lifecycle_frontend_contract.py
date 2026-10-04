"""Поля паспорта по видам правок во фронте совпадают с сервером.

Фронт держит их в frontend/src/lib/lifecycleContract.json: замороженные в
статусе паспорта части он отправляет на сервер как хранятся и не считает
несохранёнными правками. Тест не даёт копии разойтись с design/lifecycle.py —
иначе «Сохранить» утверждённого паспорта снова упадёт на FrozenDesignError.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from design.lifecycle import DESIGNED_PAYLOAD_KEYS, EXECUTION_PAYLOAD_KEYS, MEASURED_PAYLOAD_KEYS

CONTRACT = Path(__file__).resolve().parents[1] / "frontend" / "src" / "lib" / "lifecycleContract.json"


class LifecycleFrontendContractTest(unittest.TestCase):
    def test_payload_keys_match_server(self) -> None:
        keys = json.loads(CONTRACT.read_text(encoding="utf-8"))["payload_keys"]
        self.assertEqual(keys["designed"], list(DESIGNED_PAYLOAD_KEYS))
        self.assertEqual(keys["execution"], list(EXECUTION_PAYLOAD_KEYS))
        self.assertEqual(keys["measured"], list(MEASURED_PAYLOAD_KEYS))
        # Название сервер сравнивает отдельно (classify_mutations → metadata).
        self.assertEqual(keys["metadata"], ["name"])


if __name__ == "__main__":
    unittest.main()
