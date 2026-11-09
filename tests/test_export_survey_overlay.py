"""DXF скважин ложится на чертёж маркшейдера без сдвига (TASK-015, PR 4, §4 «Приёмка»).

Фикстура `block66.dxf` сдвинута на секретную константу, а выгрузка SHOTPlus
блока 66 — в настоящих координатах, поэтому проверка идёт на проекте,
построенном из самого чертежа: контур 769 «блок 66 вар 2» и скважины внутри.
Выгрузка должна вернуть те же координаты, что в чертеже, до 1 мм.
"""
from __future__ import annotations

import io
from pathlib import Path

import ezdxf
import pytest
import shapely
from ezdxf.entities import LWPolyline

from design.drilling_passport import passport_context
from design.export_survey import holes_dxf
from design.models import BlastDesign, BlockContour, Hole, Point3
from design.spatial.cad.contour import ready_contour
from design.spatial.cad.reader import read_cad
from design.spatial.cad.roles import RoleParams, assign_roles

FIXTURE = Path(__file__).parent / "fixtures" / "cad" / "block66.dxf"
ELEVATION_M = 419.85
STEP_M = 3.7


@pytest.fixture(scope="module")
def ring() -> list[tuple[float, float]]:
    drawing = read_cad(FIXTURE.read_bytes(), "block66.dxf")
    assign_roles(drawing.entities, {}, RoleParams())
    contour = next(item for item in drawing.entities if item.handle == "769")
    draft = ready_contour(contour)
    assert draft.ok and draft.ring is not None, draft.issues
    return [(float(x), float(y)) for x, y in draft.ring]


def _design(ring: list[tuple[float, float]]) -> BlastDesign:
    polygon = shapely.Polygon(ring)
    start = polygon.representative_point()
    holes = []
    for index in range(10):
        x, y = start.x, start.y + (index - 5) * STEP_M
        assert polygon.contains(shapely.Point(x, y))
        holes.append(
            Hole(
                id=str(index + 1),
                row=0,
                col=index,
                collar=Point3(x, y, ELEVATION_M),
                toe=Point3(x, y, ELEVATION_M - 11.0),
                diameter_mm=140.0,
                subdrill_m=1.0,
            )
        )
    contour = BlockContour(vertices=[Point3(x, y, ELEVATION_M) for x, y in ring], name="66")
    return BlastDesign(design_id="block-66-cad", name="Блок 66", contour=contour, holes=holes)


def test_holes_dxf_lies_on_surveyor_drawing(ring):
    design = _design(ring)
    context = passport_context(design, {"block": "66"}, None, None)
    doc = ezdxf.read(io.StringIO(holes_dxf(context, revision_no=1).decode("utf-8")))
    msp = doc.modelspace()

    contour = list(msp.query('LWPOLYLINE[layer=="BLX_CONTOUR"]'))[0]
    assert isinstance(contour, LWPolyline)
    exported = [tuple(p) for p in contour.get_points("xy")]
    assert len(exported) == len(ring)
    for (x, y), (ex, ey) in zip(exported, ring):
        assert (x, y) == pytest.approx((ex, ey), abs=0.001)

    polygon = shapely.Polygon(ring)
    points = list(msp.query('POINT[layer=="BLX_HOLE"]'))
    assert len(points) == len(design.holes)
    for point, hole in zip(points, design.holes):
        location = point.dxf.location
        assert (location.x, location.y, location.z) == pytest.approx(
            (hole.collar.x, hole.collar.y, hole.collar.z), abs=0.001
        )
        assert polygon.contains(shapely.Point(location.x, location.y))
