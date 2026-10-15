#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Regression checks for through-via obstacles and plane-avoidance route costs."""
import unittest
import pcbnew
from shapely.geometry import Point, box, LineString
from route_targeted_closure import obstacles, search, make_track, vector, routing_domain


class LayerConstraints(unittest.TestCase):
    def test_via_keepout_blocks_layer_changes_without_blocking_traces(self) -> None:
        board = self.board()
        net = board.FindNet('CH000_P_MUX').GetNetCode()
        options = dict(board=board, start=(3, 8), goal=(17, 8), net=net,
                       width=.15, clearance=.15, both_layers=True, margin=7,
                       step=.5, max_nodes=10000)
        self.assertIsNotNone(search(**options, goal_layer=1))
        self.assertIsNone(search(**options, goal_layer=1, via_keepout=box(0, 0, 20, 20)))
        self.assertIsNotNone(search(**options, goal_layer=0, via_keepout=box(0, 0, 20, 20)))

    def board(self) -> pcbnew.BOARD:
        board = pcbnew.BOARD()
        for name in ('CH000_P_MUX', 'CH001_P_MUX', '3V3A'):
            board.Add(pcbnew.NETINFO_ITEM(board, name))
        corners = [(0, 0), (20, 0), (20, 20), (0, 20), (0, 0)]
        for a, z in zip(corners, corners[1:]):
            edge = pcbnew.PCB_SHAPE(board)
            edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
            edge.SetStart(vector(a)); edge.SetEnd(vector(z))
            edge.SetWidth(pcbnew.FromMM(.1)); edge.SetLayer(pcbnew.Edge_Cuts)
            board.Add(edge)
        return board

    def test_through_vias_avoid_unselected_signal_and_power_layers(self) -> None:
        board = self.board()
        own = board.FindNet('CH000_P_MUX').GetNetCode()
        foreign = board.FindNet('CH001_P_MUX').GetNetCode()
        power = board.FindNet('3V3A').GetNetCode()
        make_track(board, (1, 1), (4, 1), foreign, .15, pcbnew.F_Cu)
        make_track(board, (1, 3), (4, 3), foreign, .15, pcbnew.In2_Cu)
        make_track(board, (1, 5), (4, 5), power, .15, pcbnew.F_Cu)
        layers, vias = obstacles(board, own, .15, .15, box(0, 0, 6, 7), .6,
                                 (pcbnew.B_Cu, pcbnew.In2_Cu))
        self.assertFalse(layers[0].contains(Point(2, 2)))
        self.assertTrue(vias.contains(Point(2, 1.3)))
        self.assertTrue(vias.contains(Point(2, 3.3)))
        self.assertTrue(vias.contains(Point(2, 5.56)))
        self.assertFalse(vias.contains(Point(2, 5.59)))
        _, default_vias = obstacles(board, own, .15, .15, box(0, 0, 6, 7), .6)
        self.assertTrue(default_vias.contains(Point(2, 3.3)))

    def test_external_window_cannot_bypass_a_copper_fence(self) -> None:
        board = self.board()
        own = board.FindNet('CH000_P_MUX').GetNetCode()
        other = board.FindNet('CH001_P_MUX').GetNetCode()
        make_track(board, (10, .1), (10, 19.9), other, .15, pcbnew.F_Cu)
        window = box(-2, -2, 22, 22)
        layers, vias = obstacles(board, own, .15, .15, window, .6)
        free = window.difference(layers[0])
        component = next(g for g in getattr(free, 'geoms', [free])
                         if g.covers(Point(3, 10)))
        self.assertFalse(component.covers(Point(17, 10)))
        self.assertTrue(layers[0].covers(Point(3, -.1)))
        self.assertTrue(vias.covers(Point(3, -.1)))

    def test_vias_and_tracks_respect_cutouts_and_their_own_edge_radius(self) -> None:
        board = self.board()
        edge = pcbnew.PCB_SHAPE(board)
        edge.SetShape(pcbnew.SHAPE_T_RECT)
        edge.SetStart(vector((8, 8))); edge.SetEnd(vector((12, 12)))
        edge.SetWidth(pcbnew.FromMM(.1)); edge.SetLayer(pcbnew.Edge_Cuts)
        board.Add(edge)
        own = board.FindNet('CH000_P_MUX').GetNetCode()
        layers, vias = obstacles(board, own, .15, .15, box(-1, -1, 21, 21), .6)
        for shape in [*layers, vias]:
            self.assertTrue(shape.covers(Point(10, 10)))
        self.assertFalse(layers[0].covers(Point(.4, 5)))
        self.assertTrue(vias.covers(Point(.4, 5)))
        self.assertFalse(vias.covers(Point(.6, 5)))
        self.assertFalse(layers[0].covers(Point(7.6, 10)))
        self.assertTrue(vias.covers(Point(7.6, 10)))

    def test_missing_outline_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, 'closed board outline'):
            routing_domain(pcbnew.BOARD(), .075)

    def test_routing_cost_avoids_a_plane_when_a_same_layer_detour_exists(self) -> None:
        board = self.board()
        net = board.FindNet('CH000_P_MUX').GetNetCode()
        region = box(8, 6, 12, 10)
        common = dict(board=board, start=(3, 8), goal=(17, 8), net=net,
                      width=.15, clearance=.15, both_layers=False, margin=7,
                      step=.5, max_nodes=10000)
        direct = search(**common)
        avoided = search(**common, cost_regions=((0, region, 20),))
        self.assertIsNotNone(direct); self.assertIsNotNone(avoided)
        line = lambda path: LineString([p[1:] for p in path])
        self.assertGreater(line(direct).intersection(region).length, 3.9)
        self.assertLess(line(avoided).intersection(region).length, .01)
        self.assertGreater(line(avoided).length, line(direct).length)
        with self.assertRaises(ValueError):
            search(**common, layers=(pcbnew.F_Cu, pcbnew.In1_Cu))


if __name__ == '__main__':
    unittest.main()
