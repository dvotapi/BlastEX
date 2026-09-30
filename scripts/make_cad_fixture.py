"""Фикстура DXF из чертежа маркшейдера со сдвигом координат.

Репозиторий публичный, поэтому координаты заказчика в МСК сдвигаются на
константу: площади, длины, отметки Z, слои и handle от сдвига не меняются.
Константа — секрет: в репозитории её нет, она лежит рядом с исходником
(`Docs/specs/block66/shift.txt`, вне git). Иначе реальные координаты
восстанавливаются сложением.

DWG конвертируется тем же `dwg2dxf`, что и на сервере (полный DXF), поэтому
скрипт запускается в Docker-образе API:

    docker run --rm -v "$PWD":/w -w /w -e PYTHONPATH=/w --entrypoint python \\
        <образ API> scripts/make_cad_fixture.py \\
        --dwg "Docs/specs/block66/<файл>.dwg" --out tests/fixtures/cad/block66.dxf \\
        --dx <сдвиг X> --dy <сдвиг Y>

Проверка, что в фикстуре не осталось больших координат, —
`tests/test_cad_fixture_privacy.py`.
"""
from __future__ import annotations

import argparse
import collections
import sys
import tempfile
from pathlib import Path

import ezdxf

from design.spatial.dwg import dwg_to_dxf


def _summary(doc) -> str:
    msp = doc.modelspace()
    kinds = collections.Counter(entity.dxftype() for entity in msp)
    ext_min, ext_max = doc.header.get("$EXTMIN"), doc.header.get("$EXTMAX")
    return (
        f"сущностей: {sum(kinds.values())} {dict(sorted(kinds.items()))}; "
        f"$INSUNITS={doc.header.get('$INSUNITS')}; экстент {ext_min} … {ext_max}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dwg", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--dx", required=True, type=float)
    parser.add_argument("--dy", required=True, type=float)
    args = parser.parse_args(argv)

    dxf = dwg_to_dxf(args.dwg.read_bytes(), args.dwg.name, minimal=False)
    with tempfile.NamedTemporaryFile(suffix=".dxf") as handle:
        handle.write(dxf)
        handle.flush()
        doc = ezdxf.readfile(handle.name)
    print("исходник:", _summary(doc))
    # Полный DXF от LibreDWG ezdxf читает, но записать без аудита не может:
    # у служебных объектов (материалы и т. п.) битые ссылки. Аудит чинит только
    # таблицы объектов, геометрию он не трогает.
    auditor = doc.audit()
    print(f"аудит: исправлений {len(auditor.fixes)}, ошибок {len(auditor.errors)}")

    for entity in doc.modelspace():
        # У подписи без выравнивания точка выравнивания не задана (0; 0):
        # сдвинутая, она раскрыла бы константу. Её просто убираем.
        unaligned = entity.dxftype() == "TEXT" and not entity.dxf.get("halign", 0) and not entity.dxf.get("valign", 0)
        entity.translate(args.dx, args.dy, 0)
        if unaligned:
            entity.dxf.discard("align_point")
    # Центр активного вида хранит координаты, на которые был открыт чертёж.
    for vport in doc.viewports:
        if vport.dxf.hasattr("center"):
            center = vport.dxf.center
            cx, cy = center[0], center[1]
            vport.dxf.center = (cx + args.dx, cy + args.dy)
    for name in ("$EXTMIN", "$EXTMAX"):
        x, y, z = doc.header.get(name, (0.0, 0.0, 0.0))
        doc.header[name] = (x + args.dx, y + args.dy, z)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(args.out)
    print("фикстура:", _summary(ezdxf.readfile(args.out)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
