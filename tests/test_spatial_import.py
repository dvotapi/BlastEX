import unittest

from design.spatial.io import SurveyImportError, detect_format, import_bench_dxf, import_survey
from design.spatial.surfaces import build_surface


XYZ = """
# bench survey
0 0 100
10 0 101
10 10 102
0 10 101
5 5 101.5
"""

CSV = """easting;northing;elevation
0;0;20
20;0;21
20;20;22
0;20;21
"""

DXF = """0
SECTION
2
ENTITIES
0
POINT
8
0
10
1.0
20
2.0
30
3.0
0
LWPOLYLINE
8
0
90
2
70
0
10
0.0
20
0.0
10
4.0
20
0.0
0
ENDSEC
0
EOF
"""

GEOJSON = """
{
  "type": "FeatureCollection",
  "features": [
    {"type": "Feature", "geometry": {"type": "Point", "coordinates": [1, 2, 3]}},
    {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[0, 0, 10], [5, 0, 11], [5, 5, 12]]}}
  ]
}
"""

BENCH_DXF = """0
SECTION
2
ENTITIES
0
POLYLINE
8
верхняя бровка
0
VERTEX
10
0
20
0
30
110
0
VERTEX
10
10
20
0
30
111
0
VERTEX
10
10
20
10
30
110
0
SEQEND
0
POLYLINE
8
нижняя бровка
0
VERTEX
10
1
20
1
30
100
0
VERTEX
10
9
20
1
30
100
0
VERTEX
10
9
20
9
30
100
0
SEQEND
0
ENDSEC
0
EOF
"""


class DetectFormatTests(unittest.TestCase):
    def test_by_extension(self):
        self.assertEqual(detect_format("bench.xyz"), "xyz")
        self.assertEqual(detect_format("pts.csv"), "csv")
        self.assertEqual(detect_format("face.dxf"), "dxf")
        self.assertEqual(detect_format("block.geojson"), "geojson")

    def test_by_content(self):
        self.assertEqual(detect_format("", '{"type":"Point","coordinates":[1,2]}'), "geojson")
        self.assertEqual(detect_format("", "0 0 1\n1 1 2\n"), "xyz")


class ImportSurveyTests(unittest.TestCase):
    def test_xyz(self):
        survey = import_survey(XYZ, filename="bench.xyz")
        self.assertEqual(survey.source_format, "xyz")
        self.assertEqual(len(survey.points), 5)

    def test_csv_named_columns(self):
        survey = import_survey(CSV, filename="bench.csv")
        self.assertEqual(len(survey.points), 4)
        self.assertAlmostEqual(survey.points[0].z, 20.0)

    def test_dxf_point_and_lwpolyline(self):
        survey = import_survey(DXF, filename="face.dxf")
        self.assertGreaterEqual(len(survey.points), 3)
        self.assertTrue(survey.polylines)

    def test_geojson(self):
        survey = import_survey(GEOJSON, filename="block.geojson")
        self.assertGreaterEqual(len(survey.points), 4)
        self.assertEqual(len(survey.polylines), 1)

    def test_empty_rejected(self):
        with self.assertRaises(SurveyImportError):
            import_survey("   ")

    def test_no_coordinates_rejected(self):
        with self.assertRaises(SurveyImportError):
            import_survey("name,value\nfoo,bar\n", filename="bad.csv")

    def test_bench_dxf_extracts_named_3d_brow_lines(self):
        imported = import_bench_dxf(BENCH_DXF)
        self.assertEqual(imported.crest_layer, "верхняя бровка")
        self.assertEqual(imported.toe_layer, "нижняя бровка")
        self.assertEqual(len(imported.contour), 6)
        self.assertGreater(imported.crest_z_m, imported.toe_z_m)


class BuildSurfaceTests(unittest.TestCase):
    def test_top_surface_from_xyz(self):
        survey = import_survey(XYZ, filename="bench.xyz")
        surface = build_surface("top", survey.points, source_format="xyz", source_name="bench.xyz")
        self.assertTrue(surface.has_tin)
        self.assertEqual(surface.kind, "top")
        z = surface.elevation_at(5.0, 5.0)
        self.assertIsNotNone(z)
        self.assertGreater(z, 100.0)
        self.assertLess(z, 103.0)

    def test_unknown_kind_rejected(self):
        from design.models import Point3

        with self.assertRaises(ValueError):
            build_surface("magma", [Point3(0, 0, 0)])


if __name__ == "__main__":
    unittest.main()
