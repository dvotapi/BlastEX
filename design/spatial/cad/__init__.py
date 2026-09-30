"""Импорт чертежа маркшейдера (TASK-013): чтение DXF/DWG и роли слоёв."""
from design.spatial.cad.model import CadDrawing, CadEntity, CadWarning
from design.spatial.cad.reader import CadReadError, ReadOptions, read_cad

__all__ = ["CadDrawing", "CadEntity", "CadReadError", "CadWarning", "ReadOptions", "read_cad"]
