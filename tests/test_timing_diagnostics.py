import unittest

from Blast import ExplosiveProperties
from design.analysis import timing_diagnostics, validate
from design.models import (
    BenchSurface,
    BlastDesign,
    BlockContour,
    Connector,
    DetonatingCord,
    DownholeConnector,
    ElectronicChannel,
    HoleLoad,
    InitiationNetwork,
    Point3,
    Starter,
    SurfaceConnector,
)
from design.pattern import generate_pattern
from design.timing import (
    add_surface_tie,
    apply_electronic_timing,
    build_template_network,
    remove_surface_tie,
    resolve_network,
    toggle_starter,
)

EXPLOSIVE = ExplosiveProperties("Гранулит-РП", 0.85, 3.76)


def _holes(width=20.0, height=16.0):
    contour = BlockContour(
        vertices=[Point3(x=x, y=y, z=0.0) for x, y in [(0, 0), (width, 0), (width, height), (0, height)]],
        free_faces=[[0, 1]],
        bench=BenchSurface(crest_z_m=0.0, toe_z_m=-10.0),
    )
    holes = generate_pattern(
        contour,
        {
            "pattern": "rectangular",
            "spacing_a_m": 4.0,
            "burden_b_m": 4.0,
            "offset_from_face_m": 0.0,
            "edge_margin_m": 0.0,
        },
    )
    return contour, holes


class TimingDiagnosticTests(unittest.TestCase):
    def test_unconnected_and_isolated_branch(self):
        contour, holes = _holes()
        network = build_template_network(holes, "row", {"system": "nonel"})
        last = holes[-1]
        isolate = holes[-2]
        network.surface_connectors = [
            item for item in network.surface_connectors if item.to_hole not in {last.id, isolate.id}
        ]
        network.connectors = [
            item for item in network.connectors if item.to_hole not in {last.id, isolate.id}
        ]
        add_surface_tie(network, isolate.id, last.id, 25.0)
        network.starter_items = [item for item in network.starter_items if item.hole_id not in {last.id, isolate.id}]
        network.starters = [item for item in network.starters if item not in {last.id, isolate.id}]
        design = BlastDesign(design_id="d", contour=contour, holes=holes, network=network)
        result = resolve_network(network, holes)
        warnings = validate(design)
        codes = {item["code"] for item in warnings}
        self.assertIn("unconnected_holes", codes)
        self.assertIn("isolated_network_branches", codes)
        self.assertNotIn(last.id, result.times_ms)

    def test_duplicate_times_and_high_mic(self):
        contour, holes = _holes()
        times = {hole.id: 0.0 for hole in holes}
        loads = [HoleLoad(hole_id=hole.id, total_charge_kg=800.0) for hole in holes]
        design = BlastDesign(
            design_id="d",
            contour=contour,
            holes=holes,
            loads=loads,
            network=InitiationNetwork(
                system="electronic",
                electronic_times_ms=times,
                electronic_channels=[
                    ElectronicChannel(id=f"ch-{hole.id}", hole_id=hole.id, time_ms=0.0) for hole in holes
                ],
                starter_items=[Starter(id="st", hole_id=holes[0].id)],
            ),
        )
        warnings = timing_diagnostics(design, times, high_mic_kg=100.0, high_mic_fraction=0.01)
        codes = {item["code"] for item in warnings}
        self.assertIn("duplicate_times", codes)
        self.assertIn("high_mic", codes)

    def test_insufficient_delays_and_relief_direction(self):
        contour, holes = _holes()
        by_row = {}
        for hole in holes:
            by_row.setdefault(hole.row, []).append(hole)
        front = by_row[min(by_row)]
        back = by_row[max(by_row)]
        times = {hole.id: 100.0 for hole in holes}
        for hole in front:
            times[hole.id] = 200.0
        for hole in back:
            times[hole.id] = 0.0
        # Neighbours in the same row get a tiny delay so insufficient_delays fires.
        times[front[0].id] = 200.0
        times[front[1].id] = 201.0
        design = BlastDesign(
            design_id="d",
            contour=contour,
            holes=holes,
            network=InitiationNetwork(system="electronic", electronic_times_ms=times),
            pattern_params={"spacing_a_m": 4.0, "burden_b_m": 4.0},
        )
        warnings = timing_diagnostics(design, times, min_delay_ms=8.0)
        codes = {item["code"] for item in warnings}
        self.assertIn("insufficient_delays", codes)
        self.assertTrue("relief_direction" in codes or "unexpected_firing_order" in codes)

    def test_manual_tie_edit_round_trip(self):
        _contour, holes = _holes()
        network = InitiationNetwork(system="nonel")
        add_surface_tie(network, holes[0].id, holes[1].id, 42.0)
        self.assertEqual(len(network.surface_connectors), 1)
        self.assertEqual(network.connectors[0].delay_ms, 42.0)
        toggle_starter(network, holes[0].id)
        self.assertEqual(network.starters, [holes[0].id])
        remove_surface_tie(network, network.surface_connectors[0].id)
        self.assertEqual(network.surface_connectors, [])

    def test_electronic_modes_and_expression(self):
        _contour, holes = _holes()
        row_net = apply_electronic_timing(holes, "row", {"interval_ms": 10.0, "base_ms": 0.0})
        times = {hole.id: next(ch.time_ms for ch in row_net.electronic_channels if ch.hole_id == hole.id) for hole in holes}
        by_row = {}
        for hole in holes:
            by_row.setdefault(hole.row, set()).add(times[hole.id])
        for values in by_row.values():
            self.assertEqual(len(values), 1)

        selected = [holes[0].id, holes[3].id, holes[5].id]
        sel_net = apply_electronic_timing(
            holes, "selection", {"interval_ms": 17.0, "selected_hole_ids": selected}
        )
        self.assertAlmostEqual(sel_net.electronic_times_ms[selected[0]], 0.0)
        self.assertAlmostEqual(sel_net.electronic_times_ms[selected[2]], 34.0)

        expr_net = apply_electronic_timing(
            holes,
            "expression",
            {"timing_expression": "interval * row + col", "interval_ms": 10.0},
        )
        sample = holes[0]
        self.assertAlmostEqual(expr_net.electronic_times_ms[sample.id], 10.0 * sample.row + sample.col)

        v_net = apply_electronic_timing(holes, "v_pattern", {"interval_ms": 10.0})
        diag_net = apply_electronic_timing(holes, "diagonal", {"interval_ms": 10.0})
        self.assertNotEqual(v_net.electronic_times_ms, diag_net.electronic_times_ms)

        direction = apply_electronic_timing(holes, "direction", {"interval_ms": 50.0, "direction_azimuth_deg": 90.0})
        gradient = apply_electronic_timing(holes, "gradient", {"gradient_from_ms": 0.0, "gradient_to_ms": 100.0})
        self.assertEqual(len(direction.electronic_channels), len(holes))
        self.assertEqual(len(gradient.electronic_channels), len(holes))

    def test_deck_and_primer_firing_events(self):
        contour, holes = _holes()
        hole = holes[0]
        load = HoleLoad(
            hole_id=hole.id,
            total_charge_kg=40.0,
            decks=[
                {"kind": "stemming", "from_m": 0, "to_m": 3, "mass_kg": 0},
                {"kind": "bulk_explosive", "from_m": 3, "to_m": 7, "mass_kg": 20},
                {"kind": "bulk_explosive", "from_m": 8, "to_m": 12, "mass_kg": 20},
            ],
        )
        # HoleLoad.from_dict-style via constructor expects Deck objects — use from_dict.
        from design.models import Deck, Primer

        load = HoleLoad(
            hole_id=hole.id,
            total_charge_kg=40.0,
            decks=[
                Deck(kind="stemming", from_m=0, to_m=3),
                Deck(kind="bulk_explosive", from_m=3, to_m=7, mass_kg=20),
                Deck(kind="bulk_explosive", from_m=8, to_m=12, mass_kg=20),
            ],
            primers=[10.0],
            primer_items=[Primer(position_m=10.0, mass_kg=0.4)],
        )
        network = InitiationNetwork(
            system="electronic",
            starters=[hole.id],
            starter_items=[Starter(id="st", hole_id=hole.id)],
            electronic_times_ms={hole.id: 100.0},
            electronic_channels=[
                ElectronicChannel(id="ch", hole_id=hole.id, time_ms=100.0),
                ElectronicChannel(id="ch-d1", hole_id=hole.id, time_ms=125.0, deck_index=1),
                ElectronicChannel(id="ch-p0", hole_id=hole.id, time_ms=140.0, primer_index=0),
            ],
            downhole_connectors=[
                DownholeConnector(id="dh-d2", hole_id=hole.id, delay_ms=50.0, deck_index=2),
            ],
        )
        result = resolve_network(network, [hole], [load])
        levels = {(event.level, event.deck_index, event.primer_index): event.time_ms for event in result.events}
        self.assertAlmostEqual(levels[("hole", None, None)], 100.0)
        self.assertAlmostEqual(levels[("deck", 1, None)], 125.0)
        self.assertAlmostEqual(levels[("deck", 2, None)], 150.0)
        self.assertAlmostEqual(levels[("primer", None, 0)], 140.0)

    def test_detonating_cord_connects_holes(self):
        contour, holes = _holes()
        first, second = holes[0], holes[1]
        network = InitiationNetwork(
            system="detcord",
            starters=[first.id],
            starter_items=[Starter(id="st", hole_id=first.id)],
            detonating_cords=[DetonatingCord(id="dc", hole_ids=[first.id, second.id], velocity_m_s=7000.0)],
        )
        result = resolve_network(network, [first, second])
        self.assertEqual(result.warnings, [])
        self.assertIn(second.id, result.times_ms)
        self.assertGreaterEqual(result.times_ms[second.id], result.times_ms[first.id])

    def test_legacy_connector_still_resolves(self):
        _contour, holes = _holes()
        network = InitiationNetwork(
            system="nonel",
            starters=[holes[0].id],
            connectors=[Connector(from_hole=holes[0].id, to_hole=holes[1].id, delay_ms=25.0)],
        )
        network.hydrate_from_legacy()
        result = resolve_network(network, holes[:2])
        self.assertEqual(result.warnings, [])
        self.assertAlmostEqual(result.times_ms[holes[1].id], 25.0)


if __name__ == "__main__":
    unittest.main()
