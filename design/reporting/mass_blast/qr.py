"""QR наряда-путёвки (TASK-018 PR 7, §6): та же строка JWS, что принял MagEX.

Символ — 40 × 40 мм без масштабирования, уровень коррекции L, байтовый режим
(строка JWS — только ASCII), белое поле 4 модуля вокруг (спецификация QR).
Кодировщик — `reportlab.graphics.barcode.qrencoder` (новой зависимости нет);
модули рисуются прямоугольниками, ряды подряд идущих — одним.
"""
from __future__ import annotations

from reportlab.graphics.barcode import qrencoder
from reportlab.lib.colors import black, white
from reportlab.lib.units import mm
from reportlab.platypus import Flowable

__all__ = ["QR_QUIET_MODULES", "QR_SIZE", "QrFlowable", "qr_matrix"]

QR_SIZE = 40 * mm
QR_QUIET_MODULES = 4


def qr_matrix(value: str) -> list[list[bool]]:
    """Матрица модулей QR (уровень L, версия — наименьшая, в какую строка помещается)."""

    code = qrencoder.QRCode(None, qrencoder.QRErrorCorrectLevel.L)
    code.addData(value)
    code.make()
    count = code.getModuleCount()
    return [[bool(code.isDark(row, col)) for col in range(count)] for row in range(count)]


class QrFlowable(Flowable):
    """Символ QR стороной `size` (без белого поля) и белое поле вокруг."""

    def __init__(self, value: str, size: float = QR_SIZE) -> None:
        super().__init__()
        self.value = value
        self.size = size
        self.matrix = qr_matrix(value)
        self.module = size / len(self.matrix)
        self.quiet = QR_QUIET_MODULES * self.module
        self.width = self.height = size + 2 * self.quiet

    def wrap(self, available_width: float, available_height: float) -> tuple[float, float]:
        return self.width, self.height

    def draw(self) -> None:
        canvas = self.canv
        canvas.saveState()
        canvas.setFillColor(white)
        canvas.rect(0, 0, self.width, self.height, stroke=0, fill=1)
        canvas.setFillColor(black)
        count = len(self.matrix)
        for row, cells in enumerate(self.matrix):
            y = self.quiet + (count - row - 1) * self.module
            col = 0
            while col < count:
                if not cells[col]:
                    col += 1
                    continue
                start = col
                while col < count and cells[col]:
                    col += 1
                canvas.rect(self.quiet + start * self.module, y, (col - start) * self.module, self.module, stroke=0, fill=1)
        canvas.restoreState()
