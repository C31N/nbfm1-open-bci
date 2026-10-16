# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Path safety contracts for the optional Shapely 2.1 proposal engine."""
import unittest
import shapely
from unittest.mock import patch
from shapely.geometry import box, Polygon, LineString
import pcbnew
from escape_mesh import mesh_route

class Board:
    def GetTracks(self):return []

@unittest.skipUnless(hasattr(shapely,'constrained_delaunay_triangles'),'optional Shapely 2.1 mesh runtime required')
class MeshSafety(unittest.TestCase):
    def route(self,blocked,via,power,allow=True):
        with patch('escape_mesh.obstacles',return_value=(blocked,via)):
            return mesh_route(Board(),(1,5),(9,5),1,(pcbnew.F_Cu,pcbnew.B_Cu),
                              power,box(0,0,10,10),allow_vias=allow)

    def test_narrow_corridor_without_grid(self):
        obstacles=box(4,0,6,4.99).union(box(4,5.01,6,10))
        path=self.route([obstacles,box(0,0,10,10)],Polygon(),Polygon(),False)
        self.assertIsNotNone(path)
        self.assertTrue(all(not LineString([a[1:],b[1:]]).intersects(obstacles)
                            for a,b in zip(path,path[1:])))

    def test_disconnected_planar_path_is_rejected(self):
        wall=box(4,0,6,10)
        self.assertIsNone(self.route([wall,Polygon()],Polygon(),Polygon(),False))

    def test_via_transitions_have_full_paths(self):
        wall=box(4,0,6,10)
        path=self.route([wall,Polygon()],Polygon(),Polygon())
        self.assertIsNotNone(path)
        transitions=[a for a,b in zip(path,path[1:]) if a[0]!=b[0]]
        self.assertEqual(len(transitions),2)
        self.assertEqual(path[0],(0,1.,5.));self.assertEqual(path[-1],(0,9.,5.))

    def test_power_keepout_forbids_the_only_transition(self):
        wall=box(4,0,6,10)
        self.assertIsNone(self.route([wall,Polygon()],Polygon(),box(0,0,10,10)))

    def test_inner_track_cannot_cross_power_outline(self):
        with patch('escape_mesh.obstacles',return_value=([Polygon(),Polygon()],Polygon())):
            path=mesh_route(Board(),(1,5),(9,5),1,(pcbnew.B_Cu,pcbnew.In2_Cu),
                            box(4,0,6,10),box(0,0,10,10),start_layer=1,goal_layer=1,
                            allow_vias=False)
        self.assertIsNone(path)

if __name__=='__main__':unittest.main()
