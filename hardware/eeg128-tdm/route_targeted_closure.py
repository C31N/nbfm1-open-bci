#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Guarded AP1-AP4 plane escapes and obstacle-aware L1/L4 signal routing.

No footprints, net assignments, clearances, L2 or L3 zone outlines are changed.
Explicit engineering options add scoped power-width exceptions only.
Every candidate is refilled and accepted only after native KiCad 8 DRC shows
zero violations/warnings and strictly fewer airwires. This is an engineering
router, not a signal-integrity or manufacturing-release certification.
"""
from __future__ import annotations
import argparse
import heapq
import itertools
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from typing import Any

import numpy as np
import pcbnew
from native_connectivity import regressed_nets
from shapely import contains_xy, prepare
from shapely.geometry import Point, LineString, box
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

POWER = {'3V3A', '3V3D', '5V_ISO', 'VREG_1V1'}
ANALOG_REFERENCE = {'VCM','VCM_RAW','ADC_REFIN','ADS_CAP','DRL','DRL_LIMITED_1',
                    'DRL_OP_OUT','DRL_SUM','CMS1','CMS1_BUF','CMS2','CMS2_BUF'}
LAYERS = (pcbnew.F_Cu, pcbnew.B_Cu)
PROJECT_SNAPSHOTS = {}
ROUTING_GRID = .1
Point2 = tuple[float, float]
GridNode = tuple[int, int, int]
RoutingPath = list[tuple[int, float, float]]
Report = dict[str, Any]


def xy(point: pcbnew.VECTOR2I) -> Point2:
    return (pcbnew.ToMM(point.x), pcbnew.ToMM(point.y))


def vector(point: Point2) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(*(pcbnew.FromMM(float(n)) for n in point))


def metrics(report: Report) -> dict[str, int]:
    return {'violations': len(report['violations']),
            'warnings': sum(i['severity'] == 'warning' for i in report['violations'] + report['unconnected_items']),
            'unconnected': len(report['unconnected_items'])}


def native(board_path: Path, report_path: Path, refill: bool = True) -> Report:
    # LoadBoard of an accepted/trial basename can create a default project in
    # KiCad's process-global project manager. Keep the real netclass settings
    # immutable across SaveBoard and before every authoritative CLI DRC.
    project = board_path.with_suffix('.kicad_pro')
    key = board_path.parent.resolve()
    if key not in PROJECT_SNAPSHOTS:
        PROJECT_SNAPSHOTS[key] = project.read_text()
    project.write_text(PROJECT_SNAPSHOTS[key])
    if refill:
        board = pcbnew.LoadBoard(str(board_path))
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        pcbnew.SaveBoard(str(board_path), board)
    project.write_text(PROJECT_SNAPSHOTS[key])
    cmd = ['kicad-cli', 'pcb', 'drc', '--format', 'json', '--severity-all',
           '--all-track-errors', '--output', str(report_path), str(board_path)]
    report_path.unlink(missing_ok=True)
    result = subprocess.run(cmd, capture_output=True, text=True)
    project.write_text(PROJECT_SNAPSHOTS[key])
    if result.returncode not in (0, 5) or not report_path.exists():
        raise RuntimeError(f'Native DRC failed: {result.returncode}: {result.stdout} {result.stderr}')
    report = json.loads(report_path.read_text())
    if not report.get('kicad_version', '').startswith('8.'):
        raise RuntimeError('Native KiCad 8 required')
    return report


def net_of(airwire: Report) -> str:
    names = {re.search(r'\[([^]]+)\]', i['description']).group(1)
             for i in airwire['items'] if '[' in i['description']}
    if len(names) != 1:
        raise RuntimeError('Ambiguous native airwire net')
    return next(iter(names))


def objects(board: pcbnew.BOARD) -> dict[str, pcbnew.BOARD_CONNECTED_ITEM]:
    return {i.m_Uuid.AsString(): i for i in itertools.chain(
        board.GetTracks(), (p for f in board.GetFootprints() for p in f.Pads()))}


def points(item: pcbnew.BOARD_CONNECTED_ITEM) -> list[Point2]:
    if isinstance(item, pcbnew.PCB_TRACK) and not isinstance(item, pcbnew.PCB_VIA):
        start, end = xy(item.GetStart()), xy(item.GetEnd())
        # Existing trunks can be branched along their length, not only at ends.
        # Sampling keeps the search bounded; native connectivity validates taps.
        steps = min(20, max(1, math.ceil(math.dist(start, end)/2)))
        return [(start[0]+(end[0]-start[0])*i/steps,
                 start[1]+(end[1]-start[1])*i/steps) for i in range(steps+1)]
    return [xy(item.GetPosition())]


def connected_anchors(board: pcbnew.BOARD, item: pcbnew.BOARD_CONNECTED_ITEM) -> RoutingPath:
    """Copper-component anchors without transient SWIG connectivity vectors.

    KiCad's nearest displayed airwire endpoint can hide an existing escape via
    or a much less congested trunk elsewhere in the same component.

    Pad/arc boxes are conservative proposals; native DRC, including a strictly
    reduced unconnected count, is the authority for every actual new branch.
    """
    code=item.GetNetCode()
    if not hasattr(board,'_routing_anchor_cache'): board._routing_anchor_cache={}
    if code not in board._routing_anchor_cache:
        rows=[]
        for current in itertools.chain(board.GetTracks(),(p for f in board.GetFootprints() for p in f.Pads())):
            if current.GetNetCode()!=code: continue
            layers={i for i,l in enumerate(LAYERS) if current.IsOnLayer(l)}
            if not layers: continue
            if isinstance(current,pcbnew.PCB_VIA):
                shape=Point(xy(current.GetPosition())).buffer(pcbnew.ToMM(current.GetWidth())/2)
            elif isinstance(current,pcbnew.PCB_TRACK) and not isinstance(current,pcbnew.PCB_ARC):
                shape=LineString([xy(current.GetStart()),xy(current.GetEnd())]).buffer(pcbnew.ToMM(current.GetWidth())/2)
            else:
                bounds=current.GetBoundingBox()
                shape=box(pcbnew.ToMM(bounds.GetX()),pcbnew.ToMM(bounds.GetY()),
                          pcbnew.ToMM(bounds.GetRight()),pcbnew.ToMM(bounds.GetBottom()))
            rows.append((current.m_Uuid.AsString(),layers,shape,points(current)))
        board._routing_anchor_cache[code]=rows
    rows=board._routing_anchor_cache[code]
    queue=[i for i,row in enumerate(rows) if row[0]==item.m_Uuid.AsString()]
    seen=set();result=set()
    while queue:
        index=queue.pop()
        if index in seen: continue
        seen.add(index); _,layers,shape,anchors=rows[index]
        result.update((layer,*point) for layer in layers for point in anchors)
        queue.extend(j for j,row in enumerate(rows) if j not in seen and layers & row[1]
                     and shape.distance(row[2])<.00002)
    return sorted(result)


def has_plane_contact(board: pcbnew.BOARD, item: pcbnew.BOARD_CONNECTED_ITEM, layer: int) -> bool:
    """Skip redundant drops on copper already tied to its matching plane."""
    anchors = {tuple(p[1:]) for p in connected_anchors(board,item)}
    for via in board.GetTracks():
        if not isinstance(via,pcbnew.PCB_VIA) or via.GetNetCode()!=item.GetNetCode(): continue
        if xy(via.GetPosition()) not in anchors: continue
        if any(z.GetNetCode()==item.GetNetCode() and z.IsOnLayer(layer)
               and z.HitTestFilledArea(layer,via.GetPosition()) for z in board.Zones()): return True
    return False


def make_track(board: pcbnew.BOARD, start: Point2, end: Point2, net: int, width: float, layer: int) -> None:
    if math.dist(start, end) < .001:
        return
    track = pcbnew.PCB_TRACK(board)
    track.SetStart(vector(start)); track.SetEnd(vector(end))
    track.SetWidth(pcbnew.FromMM(width)); track.SetLayer(layer); track.SetNetCode(net)
    board.Add(track)


def make_via(board: pcbnew.BOARD, point: Point2, net: int, diameter: float = .65) -> None:
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(vector(point)); via.SetWidth(pcbnew.FromMM(diameter))
    via.SetDrill(pcbnew.FromMM(.30)); via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); via.SetNetCode(net)
    board.Add(via)


def obstacles(board: pcbnew.BOARD, net: int, width: float, clearance: float, window: BaseGeometry,
              via_diameter: float = .65,
              layers: tuple[int, int] | None = None) -> tuple[list[BaseGeometry], BaseGeometry]:
    """Conservative pad boxes; exact buffered track/via obstacles.

    Native DRC is authoritative for rotated/custom pads, holes, arcs and zones.
    Pad boxes overestimate rotated-pad outlines rather than underestimating them.
    """
    if via_diameter < .60:
        raise ValueError('Engineering escape vias require at least 0.60 mm diameter')
    layers = LAYERS if layers is None else layers
    via_radius = via_diameter / 2
    by_layer = [[], []]
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            if pad.GetNetCode() == net:
                continue
            neighbor_clearance=max(clearance,.20 if pad.GetNetname() in POWER | ANALOG_REFERENCE else .15)
            bounds = pad.GetBoundingBox()
            shape = box(pcbnew.ToMM(bounds.GetX()), pcbnew.ToMM(bounds.GetY()),
                        pcbnew.ToMM(bounds.GetRight()), pcbnew.ToMM(bounds.GetBottom()))
            if not shape.intersects(window):
                continue
            for index, layer in enumerate(layers):
                if pad.IsOnLayer(layer):
                    by_layer[index].append(shape.buffer(neighbor_clearance + width / 2 - 1e-9))
    via_obstacles = []
    for track in board.GetTracks():
        if isinstance(track, pcbnew.PCB_VIA):
            # Same-net copper may overlap, but drilled holes still need spacing.
            via_obstacles.append(Point(xy(track.GetPosition())).buffer(
                pcbnew.ToMM(track.GetDrillValue()) / 2 + .15 + .255))
        if track.GetNetCode() == net:
            continue
        neighbor_clearance=max(clearance,.20 if track.GetNetname() in POWER | ANALOG_REFERENCE else .15)
        radius = pcbnew.ToMM(track.GetWidth()) / 2
        if isinstance(track, pcbnew.PCB_VIA):
            shape = Point(xy(track.GetPosition())).buffer(radius)
            indices = [0, 1]
        elif isinstance(track, pcbnew.PCB_ARC):
            bounds = track.GetBoundingBox()
            shape = box(pcbnew.ToMM(bounds.GetX()), pcbnew.ToMM(bounds.GetY()),
                        pcbnew.ToMM(bounds.GetRight()), pcbnew.ToMM(bounds.GetBottom()))
            indices = [i for i, layer in enumerate(layers) if track.GetLayer() == layer]
        else:
            shape = LineString([xy(track.GetStart()), xy(track.GetEnd())]).buffer(radius)
            indices = [i for i, layer in enumerate(layers) if track.GetLayer() == layer]
        if not shape.intersects(window):
            continue
        for index in indices:
            by_layer[index].append(shape.buffer(neighbor_clearance + width / 2 - 1e-9))
        # Through vias cross all copper layers, including layers not selected
        # for this routing pass. A B.Cu/In2.Cu pass must still avoid F.Cu tracks.
        via_obstacles.append(shape.buffer(neighbor_clearance + via_radius + 1e-9))
    # No via-in-pad: keep every component pad body clear, including same-net pads.
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            b = pad.GetBoundingBox()
            neighbor_clearance=max(clearance,.20 if pad.GetNetname() in POWER | ANALOG_REFERENCE else .15)
            shape = box(pcbnew.ToMM(b.GetX()), pcbnew.ToMM(b.GetY()),
                        pcbnew.ToMM(b.GetRight()), pcbnew.ToMM(b.GetBottom()))
            if shape.intersects(window):
                via_obstacles.append(shape.buffer(via_radius + neighbor_clearance + 1e-9))
    # Apply the floating-point tolerance BEFORE union. At a legal zero-width
    # centreline corridor, touching inflated neighbours otherwise merge and
    # erase that centreline from the search model. Native DRC checks real copper.
    return [unary_union(shapes) for shapes in by_layer], unary_union(via_obstacles)


def search(board: pcbnew.BOARD, start: Point2, goal: Point2, net: int, width: float,
           clearance: float, both_layers: bool, margin: float, step: float | None = None,
           max_nodes: int = 180000, deadline: float = float('inf'), start_layer: int = 0,
           goal_layer: int = 0, reserved_bottom: BaseGeometry | None = None,
           plane_layer: int | None = None, via_diameter: float = .65,
           layers: tuple[int, int] | None = None,
           cost_regions: tuple[tuple[int, BaseGeometry, float], ...] = (),
           escape_via_only: bool = False) -> RoutingPath | None:
    if step is None: step = ROUTING_GRID
    layers = LAYERS if layers is None else layers
    if (len(layers) != 2 or layers[0] == layers[1]
            or any(layer not in (pcbnew.F_Cu, pcbnew.In2_Cu, pcbnew.B_Cu) for layer in layers)):
        raise ValueError('Route on two distinct L1/L3/L4 layers; L2 remains a ground plane')
    bounds = board.GetBoardEdgesBoundingBox()
    # Edge bounding box includes the Edge.Cuts stroke; allow another 0.15 mm.
    edge = width / 2 + .405
    x0 = max(pcbnew.ToMM(bounds.GetX()) + edge, min(start[0], goal[0]) - margin)
    y0 = max(pcbnew.ToMM(bounds.GetY()) + edge, min(start[1], goal[1]) - margin)
    x1 = min(pcbnew.ToMM(bounds.GetRight()) - edge, max(start[0], goal[0]) + margin)
    y1 = min(pcbnew.ToMM(bounds.GetBottom()) - edge, max(start[1], goal[1]) + margin)
    xx = np.arange(x0, x1 + step / 2, step); yy = np.arange(y0, y1 + step / 2, step)
    if len(xx) < 2 or len(yy) < 2:
        return None
    window = box(x0, y0, x1, y1)
    shapes, via_shape = obstacles(board, net, width, clearance, window, via_diameter, layers)
    if reserved_bottom is not None:
        shapes[1] = unary_union([shapes[1], reserved_bottom.buffer(width/2+clearance+.005)])
        via_shape = unary_union([via_shape, reserved_bottom.buffer(via_diameter/2+clearance+.005)])
    # Picometre-scale numerical tolerance resolves exact-clearance floating
    # boundaries; the unchanged native integer-unit DRC remains authoritative.
    shapes = [shape.buffer(-1e-9) for shape in shapes]
    planes = [z for z in board.Zones() if plane_layer is not None
              and z.GetNetCode()==net and z.IsOnLayer(plane_layer)]
    for shape in (*shapes, via_shape):
        prepare(shape)
    gx, gy = np.meshgrid(xx, yy)
    blocked = [contains_xy(shape, gx, gy) for shape in shapes]
    via_blocked = contains_xy(via_shape, gx, gy)
    penalties = [np.zeros(gx.shape), np.zeros(gx.shape)]
    for layer, region, weight in cost_regions:
        if layer not in (0, 1) or weight < 0 or not math.isfinite(weight):
            raise ValueError('Routing cost regions require a layer index and finite nonnegative weight')
        # Include diagonal grid edges which could cross the region between
        # two outside samples. This is a cost preference, not a DRC exception.
        penalties[layer] += contains_xy(region.buffer(step / math.sqrt(2)), gx, gy) * weight
    existing_plane_vias=[t for t in board.GetTracks() if plane_layer is not None
                         and isinstance(t,pcbnew.PCB_VIA) and t.GetNetCode()==net
                         and any(z.HitTestFilledArea(plane_layer,t.GetPosition()) for z in planes)]
    existing_goal_shape=unary_union([Point(xy(t.GetPosition())).buffer(.25) for t in existing_plane_vias])
    existing_goals=contains_xy(existing_goal_shape,gx,gy)
    via_edge = via_diameter / 2 + .25 + .105
    via_blocked |= ((gx < pcbnew.ToMM(bounds.GetX()) + via_edge)
                    | (gx > pcbnew.ToMM(bounds.GetRight()) - via_edge)
                    | (gy < pcbnew.ToMM(bounds.GetY()) + via_edge)
                    | (gy > pcbnew.ToMM(bounds.GetBottom()) - via_edge))
    def pos(n: GridNode) -> Point2: return (float(xx[n[1]]), float(yy[n[2]]))
    def anchors(point: Point2, layer: int) -> list[GridNode]:
        ix = int(round((point[0] - x0) / step)); iy = int(round((point[1] - y0) / step))
        result = []
        for dx, dy in itertools.product(range(-2, 3), repeat=2):
            x, y = ix + dx, iy + dy
            if 0 <= x < len(xx) and 0 <= y < len(yy) and not blocked[layer][y, x]:
                n = (layer, x, y)
                line = LineString([point, pos(n)])
                # Contact with an expanded obstacle boundary is legal at the
                # exact native clearance; only interior penetration blocks it.
                if not line.relate_pattern(shapes[layer], 'T********'): result.append(n)
        return result
    starts, goals = anchors(start, start_layer), set(anchors(goal, goal_layer))
    if not starts or (plane_layer is None and not escape_via_only and not goals):
        return None
    def heuristic(n: GridNode) -> float:
        p = pos(n)
        if escape_via_only:
            return 0.0
        if plane_layer is not None:
            distances=[]
            for z in planes:
                bb=z.GetBoundingBox()
                dx=max(pcbnew.ToMM(bb.GetX())-p[0],0,p[0]-pcbnew.ToMM(bb.GetRight()))
                dy=max(pcbnew.ToMM(bb.GetY())-p[1],0,p[1]-pcbnew.ToMM(bb.GetBottom()))
                distances.append(math.hypot(dx,dy))
            return min(distances,default=float('inf'))
        return math.dist(p, goal) + (2.0 if n[0] != goal_layer else 0)
    queue, costs, previous = [], {}, {}
    for n in starts:
        costs[n] = math.dist(start, pos(n)); previous[n] = None
        heapq.heappush(queue, (costs[n] + heuristic(n), costs[n], n))
    moves = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]
    expanded = 0
    while queue and expanded < max_nodes:
        if expanded % 1000 == 0 and time.monotonic() >= deadline:
            return None
        _, cost, n = heapq.heappop(queue)
        if cost != costs[n]: continue
        expanded += 1
        existing_reached=plane_layer is not None and existing_goals[n[2],n[1]]
        reached = (not via_blocked[n[2],n[1]] if escape_via_only else
                   n in goals if plane_layer is None else
                   existing_reached or not via_blocked[n[2],n[1]]
                   and any(z.HitTestFilledArea(plane_layer,vector(pos(n))) for z in planes))
        if reached:
            final_point = ((n[0],*pos(n)) if escape_via_only else
                           (goal_layer,*goal) if plane_layer is None else (n[0],*pos(n)))
            if existing_reached:
                via=min(existing_plane_vias,key=lambda t:math.dist(pos(n),xy(t.GetPosition())))
                final_point=(n[0],*xy(via.GetPosition()))
            path = []
            while n is not None:
                path.append((n[0], *pos(n))); n = previous[n]
            path.reverse()
            return [(start_layer, *start)] + path + [final_point]
        layer, x, y = n
        neighbors = []
        for dx, dy in moves:
            ax, ay = x + dx, y + dy
            if not (0 <= ax < len(xx) and 0 <= ay < len(yy)) or blocked[layer][ay, ax]: continue
            if dx and dy and (blocked[layer][y, ax] or blocked[layer][ay, x]): continue
            m = (layer, ax, ay)
            preferred = (dy == 0 if layer == 0 else dx == 0)
            neighbors.append((m, step * math.hypot(dx, dy) * (1 if preferred else 1.2)
                              * (1 + penalties[layer][ay, ax])))
        if both_layers and not via_blocked[y, x] and not blocked[1-layer][y, x]:
            # Enforce drill separation between successive proposed transitions.
            cursor, last_via = n, None
            for _ in range(20):
                parent = previous[cursor]
                if parent is None: break
                if parent[0] != cursor[0]:
                    last_via = pos(cursor); break
                cursor = parent
            if last_via is None or math.dist(pos(n), last_via) >= .56:
                neighbors.append(((1-layer, x, y), 2.0))
        for m, increment in neighbors:
            new_cost = cost + increment
            if new_cost < costs.get(m, float('inf')):
                # Raster search proposes paths only. Full native DRC below rejects
                # any continuous-edge collision missed by the grid approximation.
                costs[m] = new_cost; previous[m] = n
                heapq.heappush(queue, (new_cost + heuristic(m), new_cost, m))
    return None


def add_path(board: pcbnew.BOARD, path: RoutingPath, net: int, width: float,
             via_diameter: float = .65, layers: tuple[int, int] | None = None) -> int:
    if via_diameter < .60:
        raise ValueError('Engineering escape vias require at least 0.60 mm diameter')
    layers = LAYERS if layers is None else layers
    # Compress collinear grid steps, retaining every layer transition exactly.
    clean = []
    for p in path:
        if clean and p == clean[-1]: continue
        if len(clean) >= 2 and p[0] == clean[-1][0] == clean[-2][0]:
            a, b = clean[-2], clean[-1]
            if abs((b[1]-a[1])*(p[2]-b[2])-(b[2]-a[2])*(p[1]-b[1])) < 1e-8:
                clean.pop()
        clean.append(p)
    vias = set()
    for a, b in zip(clean, clean[1:]):
        if a[0] != b[0]:
            point = (a[1], a[2])
            if point not in vias: make_via(board, point, net, via_diameter); vias.add(point)
        else:
            make_track(board, a[1:], b[1:], net, width, layers[a[0]])
    return len(vias)


def native_fresh(board_path: Path, report_path: Path) -> Report:
    """Verify disk copper in a new process, without live routing SWIG boards."""
    module_dir = str(Path(__file__).resolve().parent)
    code = (f'import sys;sys.path.insert(0,{module_dir!r});from pathlib import Path;'
            'from route_targeted_closure import native;'
            f'native(Path({str(board_path)!r}),Path({str(report_path)!r}))')
    with report_path.with_suffix('.log').open('w') as log:
        subprocess.run([sys.executable,'-c',code],stdout=log,stderr=subprocess.STDOUT,check=True)
    return json.loads(report_path.read_text())


def apply_candidate(board_path: Path, payload_path: Path) -> None:
    """Mutate one canonical board per process; save before process teardown."""
    data=json.loads(payload_path.read_text())
    board=pcbnew.LoadBoard(str(board_path))
    proposal=data['proposal'];code=data['net_code'];width=data['width']
    necks={tuple(exit_point):tuple(start) for exit_point,start in data['necks']}
    if proposal[0]=='relocate-via':
        via=objects(board).get(proposal[1])
        if not isinstance(via,pcbnew.PCB_VIA):raise RuntimeError('Relocation UUID is not a via')
        old=xy(via.GetPosition());new=tuple(proposal[2]);layers=set()
        if math.dist(old,new)>.5:raise RuntimeError('Local via relocation exceeds 0.5 mm')
        for track in list(board.GetTracks()):
            if isinstance(track,pcbnew.PCB_VIA) or track.GetNetCode()!=via.GetNetCode():continue
            at_start=math.dist(xy(track.GetStart()),old)<.000002
            at_end=math.dist(xy(track.GetEnd()),old)<.000002
            if not (at_start or at_end):continue
            if isinstance(track,pcbnew.PCB_ARC):raise RuntimeError('Arc relocation unsupported')
            if len(proposal)>3 and track.GetLayer()==pcbnew.B_Cu:
                far=xy(track.GetEnd() if at_start else track.GetStart())
                length=math.dist(far,old);distance=float(proposal[3])
                if not .1<=distance<=1.5:raise RuntimeError('Local bend distance outside bounds')
                if length>distance*2:
                    bend=tuple(old[i]+(far[i]-old[i])*distance/length for i in (0,1))
                    if at_start:track.SetStart(vector(bend))
                    if at_end:track.SetEnd(vector(bend))
                    make_track(board,bend,new,via.GetNetCode(),pcbnew.ToMM(track.GetWidth()),track.GetLayer())
                    layers.add(track.GetLayer());continue
            if at_start:track.SetStart(vector(new))
            if at_end:track.SetEnd(vector(new))
            layers.add(track.GetLayer())
        if layers!={pcbnew.F_Cu,pcbnew.B_Cu}:
            plane_layer=pcbnew.In1_Cu if via.GetNetname()=='AGND' else pcbnew.In2_Cu
            domains={'AGND','3V3A','3V3D','5V_ISO'}
            contacts=[z for z in board.Zones() if z.GetNetCode()==via.GetNetCode()
                      and z.IsOnLayer(plane_layer) and z.HitTestFilledArea(plane_layer,vector(old))]
            if (not layers or via.GetNetname() not in domains
                    or not any(z.HitTestFilledArea(plane_layer,vector(new)) for z in contacts)):
                raise RuntimeError('Via must retain both outer layers or its existing plane domain')
        via.SetPosition(vector(new))
    elif proposal[0]=='replace-track-path':
        track=objects(board).get(proposal[1]);path=proposal[2]
        if (not isinstance(track,pcbnew.PCB_TRACK) or isinstance(track,pcbnew.PCB_VIA)
                or isinstance(track,pcbnew.PCB_ARC)):
            raise RuntimeError('Local detour requires a straight track')
        if math.dist(path[0],xy(track.GetStart()))>.000002 or math.dist(path[-1],xy(track.GetEnd()))>.000002:
            raise RuntimeError('Local detour must preserve both original endpoints')
        layer=track.GetLayer();net=track.GetNetCode();nominal=pcbnew.ToMM(track.GetWidth())
        track.SetEnd(vector(path[1]))
        for start,end in zip(path[1:],path[2:]):make_track(board,start,end,net,nominal,layer)
    elif proposal[0]=='local-power-escape':
        neck,outer=proposal[1:]
        if board.FindNet(code).GetNetname() not in POWER or width<.3:
            raise RuntimeError('Power escape requires its existing net and nominal outer width')
        if tuple(neck[-1])!=tuple(outer[0]):raise RuntimeError('Power neck does not join outer trace')
        for start,end in zip(neck,neck[1:]):make_track(board,start,end,code,.15,pcbnew.F_Cu)
        for start,end in zip(outer,outer[1:]):make_track(board,start,end,code,width,pcbnew.F_Cu)
        make_via(board,outer[-1],code)
    elif proposal[0]=='inner-plane-link':
        outer,inner,layer=proposal[1:]
        net=board.FindNet(code).GetNetname()
        expected=pcbnew.In1_Cu if net=='AGND' else pcbnew.In2_Cu
        if net not in {'AGND','3V3A','3V3D','5V_ISO'} or layer!=expected:
            raise RuntimeError('Inner escape does not match a supported plane domain')
        if tuple(outer[-1])!=tuple(inner[0]):
            raise RuntimeError('Outer and inner escapes do not share a via endpoint')
        if not any(z.GetNetCode()==code and z.IsOnLayer(layer)
                   and z.HitTestFilledArea(layer,vector(inner[-1])) for z in board.Zones()):
            raise RuntimeError('Inner escape does not end in its matching filled plane')
        for start,end in zip(outer,outer[1:]):make_track(board,start,end,code,width,pcbnew.F_Cu)
        make_via(board,outer[-1],code)
        for start,end in zip(inner,inner[1:]):make_track(board,start,end,code,width,layer)
    elif proposal[0]=='power-neck-bridge':
        make_track(board,proposal[1],proposal[2],code,.15,pcbnew.F_Cu)
    elif proposal[0] in ('thermal-ep57','trunk-drop'):
        make_via(board,proposal[1],code)
    elif proposal[0]=='escape':
        start=tuple(proposal[1])
        if start in necks:make_track(board,necks[start],start,code,.15,pcbnew.F_Cu)
        make_track(board,proposal[1],proposal[2],code,width,pcbnew.F_Cu)
        make_via(board,proposal[2],code)
    else:
        path=proposal[1]
        if proposal[0]=='path-junction':
            track=objects(board).get(proposal[2])
            junction=tuple(proposal[3])
            if (not isinstance(track,pcbnew.PCB_TRACK) or isinstance(track,pcbnew.PCB_VIA)
                    or isinstance(track,pcbnew.PCB_ARC) or track.GetNetCode()!=code):
                raise RuntimeError('Junction must split a straight same-net track')
            start,end=xy(track.GetStart()),xy(track.GetEnd())
            if LineString([start,end]).distance(Point(junction))>.000002:
                raise RuntimeError('Junction is not on the existing track')
            make_track(board,junction,end,code,pcbnew.ToMM(track.GetWidth()),track.GetLayer())
            track.SetEnd(vector(junction))
        for point in (tuple(path[0][1:]),tuple(path[-1][1:])):
            if point in necks:make_track(board,necks[point],point,code,.15,pcbnew.F_Cu)
        add_path(board,path,code,width)
        if proposal[0]=='escape-path':make_via(board,proposal[2],code)
    if not pcbnew.SaveBoard(str(board_path),board):raise RuntimeError('Candidate save failed')


def main() -> None:
    global ROUTING_GRID
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--board', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--seconds', type=int, default=600)
    p.add_argument('--mode', choices=['planes', 'signals', 'all'], default='all')
    p.add_argument('--candidate-offset',type=int,default=0,
                   help='Rotate equally prioritized candidates between isolated worker slices')
    p.add_argument('--only-net',action='append',default=[],
                   help='Restrict a diagnostic pass to exact net names; repeatable')
    p.add_argument('--only-reference',action='append',default=[],
                   help='Focus diagnostic passes on airwires with pads of these references')
    p.add_argument('--allow-bottom-analog', action='store_true',
                   help='Engineering experiment only; final return-path/SI review still required')
    p.add_argument('--qfn-power-neckdown', action='store_true',
                   help='Engineering-only U23 power necks: 0.15 mm width, <=0.8 mm length; no clearance relaxation')
    p.add_argument('--cluster-power-neckdown', action='store_true',
                   help='Local U1-U20 power necks: 0.15 mm width, <=0.8 mm length; clearance unchanged')
    p.add_argument('--qfn-neck-length',type=float,choices=[.8,1.2,1.6],default=.8,
                   help='Bounded local U23 neck length in mm; native rules and clearances still apply')
    p.add_argument('--max-routes', type=int, default=1000)
    p.add_argument('--connection-seconds', type=float, default=10,
                   help='Bound search time per connection so one blocked pin cannot starve the bus')
    p.add_argument('--path-seconds', type=float, default=2,
                   help='Bound each anchor-pair search; increase for targeted dense escapes')
    p.add_argument('--grid-step',type=float,choices=[.01,.025,.05,.1],default=.1,
                   help='Search raster in mm; smaller raster resolves narrow legal corridors')
    a = p.parse_args()
    a.board = a.board.resolve()
    a.output_dir = a.output_dir.resolve()
    ROUTING_GRID = a.grid_step
    a.output_dir.mkdir(parents=True, exist_ok=True)
    working = a.output_dir/'eeg128-tdm.kicad_pcb'
    shutil.copy2(a.board, working)
    for suffix in ('.kicad_pro', '.kicad_dru'):
        source = a.board.with_suffix(suffix)
        if not source.exists(): raise RuntimeError(f'Missing unchanged native rules: {source}')
        shutil.copy2(source, working.with_suffix(suffix))
    if a.qfn_power_neckdown:
        rules = working.with_suffix('.kicad_dru')
        if 'Engineering U23 local power escape neck' not in rules.read_text():
            with rules.open('a') as handle:
                handle.write('''\n(rule "Engineering U23 local power escape neck"
    (condition "A.Type == 'Track' && A.intersectsCourtyard('U23') && (A.NetName == '3V3D' || A.NetName == 'VREG_1V1')")
    (constraint track_width (min 0.15mm)))\n''')
    if a.cluster_power_neckdown:
        rules = working.with_suffix('.kicad_dru')
        if 'Engineering U1-U20 local power escape neck' not in rules.read_text():
            courtyards = ' || '.join(f"A.intersectsCourtyard('U{i}')" for i in range(1,21))
            with rules.open('a') as handle:
                handle.write('\n(rule "Engineering U1-U20 local power escape neck"\n'
                             f"    (condition \"A.Type == 'Track' && ({courtyards}) && "
                             "(A.NetName == '3V3A' || A.NetName == '3V3D' || A.NetName == '5V_ISO')\")\n"
                             '    (constraint track_width (min 0.15mm)))\n')
    report = native_fresh(working, a.output_dir/'drc-initial.json')
    if metrics(report)['violations'] or metrics(report)['warnings']:
        raise RuntimeError('Baseline must be geometrically clean')
    accepted = a.output_dir/'accepted.kicad_pcb'
    shutil.copy2(working, accepted)
    history, tried = [], set()
    deadline = time.monotonic() + a.seconds
    count = 0
    while time.monotonic() < deadline and count < a.max_routes:
        board = pcbnew.LoadBoard(str(accepted)); indexed = objects(board)
        candidates = []
        for airwire in report['unconnected_items']:
            net = net_of(airwire)
            if a.only_net and net not in a.only_net: continue
            plane = net in POWER | {'AGND'} and net != 'VREG_1V1'
            if a.mode == 'planes' and not plane or a.mode == 'signals' and plane: continue
            endpoints = [indexed.get(i['uuid']) for i in airwire['items']]
            if any(i is None for i in endpoints): continue
            if a.only_reference and not any(isinstance(e,pcbnew.PAD)
                    and e.GetParentFootprint().GetReference() in a.only_reference for e in endpoints): continue
            distance = min(math.dist(x, y) for x in points(endpoints[0]) for y in points(endpoints[1]))
            exposed_ground = net == 'AGND' and any(
                isinstance(e, pcbnew.PAD) and e.GetNumber() == '57'
                and e.GetParentFootprint().GetReference() == 'U23' for e in endpoints)
            priority = (-1 if exposed_ground else 0 if plane else 1 if net.startswith(('QSPI', 'USB')) or net == 'VREG_1V1'
                        else 2 if net.startswith('BANK') else 3 if net.startswith('MUX_') else 4)
            candidates.append((priority, distance, airwire, endpoints))
        candidates.sort(key=lambda c: (c[0], c[1]))
        if a.candidate_offset:
            rotated=[]
            for _,group in itertools.groupby(candidates,key=lambda c:c[0]):
                group=list(group); offset=a.candidate_offset%len(group)
                rotated.extend(group[offset:]+group[:offset])
            candidates=rotated
        improved = False
        for _, distance, airwire, endpoints in candidates:
            if time.monotonic() >= deadline: break
            net = net_of(airwire); code = endpoints[0].GetNetCode()
            # Local power escapes use the existing 0.30 mm minimum; the primary
            # 0.40 mm nominal distribution traces and all native rules stay intact.
            width = .3 if net in POWER else .2 if net.startswith('QSPI') else .15
            clearance = .2 if net in POWER else .15
            plane = net in POWER | {'AGND'} and net != 'VREG_1V1'
            proposals, necks = [], {}
            if (a.qfn_power_neckdown and net in POWER
                    and all(isinstance(e,pcbnew.PAD) and e.GetParentFootprint().GetReference()=='U23'
                            for e in endpoints)):
                start,goal = (xy(e.GetPosition()) for e in endpoints)
                if math.dist(start,goal)<=.8:
                    proposals.append(('power-neck-bridge',start,goal))
            if plane:
                # Tie a perimeter ground pad inward to the exposed pad instead
                # of adding another hole outside an already escaped EP.
                if net=='AGND':
                    ep=next((e for e in endpoints if isinstance(e,pcbnew.PAD)
                             and e.GetParentFootprint().GetReference()=='U23' and e.GetNumber()=='57'),None)
                    if ep is not None:
                        center=xy(ep.GetPosition())
                        for e in endpoints:
                            if not isinstance(e,pcbnew.PAD) or e.GetNumber()=='57': continue
                            if e.GetParentFootprint().GetReference()!='U23': continue
                            start=xy(e.GetPosition())
                            target=(max(center[0]-1.55,min(center[0]+1.55,start[0])),
                                    max(center[1]-1.55,min(center[1]+1.55,start[1])))
                            proposals.append(('path',[(0,*start),(0,*target)]))
                # A displayed airwire may refer to an isolated copper trunk,
                # not its original pad. Drop directly from sampled trunk copper
                # to the matching plane; native DRC rejects redundant/island vias.
                plane_layer = pcbnew.In1_Cu if net == 'AGND' else pcbnew.In2_Cu
                for endpoint in endpoints:
                    if not isinstance(endpoint, pcbnew.PCB_TRACK): continue
                    if has_plane_contact(board,endpoint,plane_layer): continue
                    for anchor in connected_anchors(board, endpoint):
                        point = anchor[1:]
                        if not any(z.GetNetCode()==code and z.IsOnLayer(plane_layer)
                                   and z.HitTestFilledArea(plane_layer,vector(point)) for z in board.Zones()): continue
                        _, via_shape = obstacles(board, code, width, clearance, Point(point).buffer(1))
                        if not via_shape.intersects(Point(point)):
                            proposals.append(('trunk-drop',point))
                escape_targets = []
                for endpoint in endpoints:
                    if not isinstance(endpoint, pcbnew.PAD): continue
                    if has_plane_contact(board,endpoint,plane_layer): continue
                    start = xy(endpoint.GetPosition())
                    footprint = endpoint.GetParentFootprint()
                    if net == 'AGND' and footprint.GetReference() == 'U23' and endpoint.GetNumber() == '57':
                        # Electrical escape of the exposed ground pad cannot pass
                        # through a closed QFN pin ring. Through-pad thermal vias
                        # need a separate paste/tenting/assembly review before release.
                        escaped=any(isinstance(t,pcbnew.PCB_VIA) and t.GetNetCode()==code
                                    and abs(xy(t.GetPosition())[0]-start[0])<1.6
                                    and abs(xy(t.GetPosition())[1]-start[1])<1.6
                                    and any(z.GetNetCode()==code and z.IsOnLayer(pcbnew.In1_Cu)
                                            and z.HitTestFilledArea(pcbnew.In1_Cu,t.GetPosition()) for z in board.Zones())
                                    for t in board.GetTracks())
                        for dx, dy in (() if escaped else ((-1.15, 1.15), (1.15, -1.15), (-1.15, -1.15), (1.15, 1.15),
                                       (0, 0), (-.8, -.8), (-.8, .8), (.8, -.8), (.8, .8))):
                            point = (start[0]+dx, start[1]+dy)
                            if any(z.GetNetCode() == code and z.IsOnLayer(pcbnew.In1_Cu)
                                   and z.HitTestFilledArea(pcbnew.In1_Cu, vector(point)) for z in board.Zones()):
                                if not any(isinstance(t, pcbnew.PCB_VIA)
                                           and math.dist(point, xy(t.GetPosition())) < .56 for t in board.GetTracks()):
                                    proposals.append(('thermal-ep57', point))
                    if (a.qfn_power_neckdown and net == '3V3D' and footprint.GetReference() == 'U23'
                            or a.cluster_power_neckdown and net in POWER
                            and footprint.GetReference() in {f'U{i}' for i in range(1,21)}):
                        center = xy(footprint.GetPosition())
                        angle=math.radians(endpoint.GetOrientation().AsDegrees())
                        sx,sy=xy(endpoint.GetSize())
                        axis=(math.cos(angle),math.sin(angle)) if sx>=sy else (-math.sin(angle),math.cos(angle))
                        sign=1 if (start[0]-center[0])*axis[0]+(start[1]-center[1])*axis[1]>=0 else -1
                        normal=tuple(round(sign*v,10) for v in axis)
                        neck_length=a.qfn_neck_length if footprint.GetReference()=='U23' else .8
                        exit_point = (start[0]+neck_length*normal[0], start[1]+neck_length*normal[1])
                        necks[exit_point] = start
                        start = exit_point
                    shape, via_shape = obstacles(board, code, width, clearance, Point(start).buffer(5))
                    for radius in (.7, 1.0, 1.4, 2.0, 2.8, 3.6, 4.5):
                        for dx, dy in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(-1,1),(1,-1),(-1,-1)):
                            target = (start[0]+radius*dx, start[1]+radius*dy)
                            layer = pcbnew.In1_Cu if net == 'AGND' else pcbnew.In2_Cu
                            if not any(z.GetNetCode() == code and z.IsOnLayer(layer)
                                       and z.HitTestFilledArea(layer, vector(target)) for z in board.Zones()): continue
                            if via_shape.intersects(Point(target)): continue
                            if shape[0].intersects(LineString([start,target])):
                                escape_targets.append((start, target))
                            else:
                                proposals.append(('escape', start, target))
                proposals = [proposal for proposal in proposals if (net, repr(proposal)) not in tried]
                if not proposals:
                    # Search for any reachable legal drop, not eight radial
                    # samples. U21 digital power lies outside its L3 domain.
                    drop_deadline=min(deadline,time.monotonic()+a.connection_seconds)
                    for endpoint in endpoints:
                        if has_plane_contact(board,endpoint,plane_layer): continue
                        anchors=connected_anchors(board,endpoint)
                        from_neck={original:exit_point for exit_point,original in necks.items()}
                        anchors=[(layer,*from_neck.get(tuple(point),tuple(point)))
                                 for layer,*point in anchors]
                        for layer,x,y in anchors[:12]:
                            start=(x,y)
                            zones=[z for z in board.Zones() if z.GetNetCode()==code and z.IsOnLayer(plane_layer)]
                            outside=min((max(pcbnew.ToMM(z.GetBoundingBox().GetX())-x,0,
                                             x-pcbnew.ToMM(z.GetBoundingBox().GetRight()),
                                             pcbnew.ToMM(z.GetBoundingBox().GetY())-y,0,
                                             y-pcbnew.ToMM(z.GetBoundingBox().GetBottom())) for z in zones),default=0)
                            margin=max(6.,outside+4.)
                            path=search(board,start,start,code,width,clearance,True,margin,
                                        deadline=drop_deadline,start_layer=layer,goal_layer=layer,
                                        plane_layer=plane_layer)
                            if path:
                                end_point=tuple(path[-1][1:])
                                existing=any(isinstance(t,pcbnew.PCB_VIA) and t.GetNetCode()==code
                                             and math.dist(end_point,xy(t.GetPosition()))<.00002 for t in board.GetTracks())
                                proposal=('path',path) if existing else ('escape-path',path,end_point)
                                if (net,repr(proposal)) not in tried:
                                    proposals.append(proposal);break
                            if time.monotonic()>=drop_deadline:break
                        if proposals or time.monotonic()>=drop_deadline:break
                if not proposals:
                    # KiCad may display a distant representative endpoint for
                    # the plane component. Reuse its nearest real plated via.
                    plane_layer=pcbnew.In1_Cu if net=='AGND' else pcbnew.In2_Cu
                    contacts=[t for t in board.GetTracks() if isinstance(t,pcbnew.PCB_VIA)
                              and t.GetNetCode()==code
                              and any(z.GetNetCode()==code and z.IsOnLayer(plane_layer)
                                      and z.HitTestFilledArea(plane_layer,t.GetPosition()) for z in board.Zones())]
                    for endpoint in endpoints:
                        if not isinstance(endpoint,pcbnew.PAD): continue
                        start=xy(endpoint.GetPosition())
                        start=next((exit_point for exit_point,original in necks.items() if original==start),start)
                        for via in sorted(contacts,key=lambda t:math.dist(start,xy(t.GetPosition())))[:4]:
                            goal=xy(via.GetPosition())
                            if math.dist(start,goal)>30: continue
                            path=search(board,start,goal,code,width,clearance,False,3.,
                                        deadline=min(deadline,time.monotonic()+a.connection_seconds))
                            if path and (net,repr(('path',path))) not in tried:
                                proposals.append(('path',path));break
                        if proposals: break
                # A plane net can also join an existing connected pad/track;
                # adding another drill is unnecessary when a local path exists.
                if not proposals:
                    start, goal = min(itertools.product(points(endpoints[0]), points(endpoints[1])),
                                      key=lambda pair: math.dist(*pair))
                    from_neck = {original: exit_point for exit_point, original in necks.items()}
                    start, goal = from_neck.get(start, start), from_neck.get(goal, goal)
                    layers = [0 if isinstance(e, pcbnew.PCB_VIA) or e.IsOnLayer(pcbnew.F_Cu)
                              else 1 if e.IsOnLayer(pcbnew.B_Cu) else None for e in endpoints]
                    if None not in layers:
                        path = search(board, start, goal, code, width, clearance, True, 3.,
                                      deadline=min(deadline, time.monotonic()+a.connection_seconds),
                                      start_layer=layers[0], goal_layer=layers[1])
                        if path: proposals.append(('path', path))
                # A clear drill site can require a bent escape around a neighbor.
                if not proposals:
                    search_deadline = min(deadline, time.monotonic() + a.connection_seconds)
                    for start, target in escape_targets[:8]:
                        path = search(board, start, target, code, width, clearance, False,
                                      3., deadline=search_deadline)
                        if path:
                            proposals.append(('escape-path', path, target))
                            break
                        if time.monotonic() >= search_deadline: break
            else:
                start, goal = min(itertools.product(points(endpoints[0]), points(endpoints[1])),
                                  key=lambda pair: math.dist(*pair))
                if a.qfn_power_neckdown and net == 'VREG_1V1':
                    adjusted = [start, goal]
                    for index, endpoint in enumerate(endpoints):
                        if not isinstance(endpoint, pcbnew.PAD): continue
                        fp = endpoint.GetParentFootprint()
                        if fp.GetReference() != 'U23': continue
                        point, center = xy(endpoint.GetPosition()), xy(fp.GetPosition())
                        dx, dy = point[0]-center[0], point[1]-center[1]
                        normal = ((math.copysign(1, dx), 0) if abs(dx) > abs(dy)
                                  else (0, math.copysign(1, dy)))
                        exit_point = (point[0]+a.qfn_neck_length*normal[0], point[1]+a.qfn_neck_length*normal[1])
                        necks[exit_point] = point
                        adjusted[index] = exit_point
                    start, goal = adjusted
                analog = net.startswith(('CH','BANK')) or re.fullmatch(r'ADC\d+_[PN]', net)
                endpoint_layers = [0 if isinstance(e, pcbnew.PCB_VIA) or e.IsOnLayer(pcbnew.F_Cu)
                                   else 1 if e.IsOnLayer(pcbnew.B_Cu) else None for e in endpoints]
                if None in endpoint_layers: continue
                search_deadline = min(deadline, time.monotonic() + a.connection_seconds)
                pairs=[((endpoint_layers[0],*start),(endpoint_layers[1],*goal))]
                if net != 'VREG_1V1':
                    # Reserve anchor pairs for each layer combination. Twelve
                    # short top-layer pairs must not hide an existing B.Cu escape.
                    anchors=[connected_anchors(board,e) for e in endpoints]
                    pairs=[]
                    for first,second in ((1,1),(0,0),(0,1),(1,0)):
                        pairs.extend(heapq.nsmallest(4,itertools.product(
                            (p for p in anchors[0] if p[0]==first),
                            (p for p in anchors[1] if p[0]==second)),
                            key=lambda pair:math.dist(pair[0][1:],pair[1][1:])))
                for anchor_start,anchor_goal in pairs:
                    start,goal=anchor_start[1:],anchor_goal[1:]
                    if analog and not a.allow_bottom_analog and (anchor_start[0] or anchor_goal[0]): continue
                    for margin in (2., 6., 12.):
                        signature = (net, anchor_start, anchor_goal, margin)
                        if signature in tried: continue
                        tried.add(signature)
                        path = search(board, start, goal, code, width, clearance,
                                      not analog or a.allow_bottom_analog, margin,
                                      deadline=min(search_deadline,time.monotonic()+a.path_seconds),
                                      start_layer=anchor_start[0], goal_layer=anchor_goal[0])
                        if path:
                            proposals.append(('path', path)); break
                        if time.monotonic() >= search_deadline: break
                    if proposals or time.monotonic() >= search_deadline: break
            for proposal in proposals:
                signature = (net, repr(proposal))
                if signature in tried: continue
                tried.add(signature)
                shutil.copy2(accepted,working)
                payload=a.output_dir/'proposal.json'
                payload.write_text(json.dumps({'proposal':proposal,'necks':list(necks.items()),
                                               'net_code':code,'width':width}))
                module_dir=str(Path(__file__).resolve().parent)
                child=(f'import sys;sys.path.insert(0,{module_dir!r});from pathlib import Path;'
                       'from route_targeted_closure import apply_candidate;'
                       f'apply_candidate(Path({str(working)!r}),Path({str(payload)!r}))')
                with (a.output_dir/'mutation.log').open('w') as log:
                    subprocess.run([sys.executable,'-c',child],stdout=log,stderr=subprocess.STDOUT,check=True)
                count += 1
                candidate_report = native_fresh(working, a.output_dir/'drc-candidate.json')
                m = metrics(candidate_report)
                regressions = regressed_nets(report, candidate_report)
                valid = (not m['violations'] and not m['warnings'] and not regressions
                         and m['unconnected'] < len(report['unconnected_items']))
                if valid:
                    # Persist before claiming acceptance in any event/report.
                    shutil.copy2(working, accepted)
                    report = candidate_report
                    shutil.copy2(a.output_dir/'drc-candidate.json', a.output_dir/'drc-accepted.json')
                    improved = True
                event = {'attempt': count, 'net': net, 'kind': proposal[0], 'accepted': valid,
                         'regressed_nets': regressions, **m}
                history.append(event); print(json.dumps(event), flush=True)
                (a.output_dir/'history.json').write_text(json.dumps(history, indent=2)+'\n')
                if valid: break
                if time.monotonic() >= deadline or count >= a.max_routes: break
            if improved or time.monotonic() >= deadline or count >= a.max_routes: break
        if not improved: break
    shutil.copy2(accepted, working)
    final = native_fresh(working, a.output_dir/'drc-final.json')
    if metrics(final) != metrics(report):
        raise RuntimeError('Saved checkpoint does not reproduce the accepted native DRC metrics')
    result = {'native_kicad_version': final['kicad_version'], **metrics(final),
              'allow_bottom_analog': a.allow_bottom_analog,
              'qfn_power_neckdown': 'Engineering U23 local power escape neck' in working.with_suffix('.kicad_dru').read_text(),
              'cluster_power_neckdown': 'Engineering U1-U20 local power escape neck' in working.with_suffix('.kicad_dru').read_text(),
              'grid_step_mm': a.grid_step,
              'engineering_only': True, 'release_authorized': False, 'history': history}
    (a.output_dir/'closure-result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k != 'history'}, indent=2))


if __name__ == '__main__':
    main()
