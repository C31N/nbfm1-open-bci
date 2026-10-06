#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Guarded AP1-AP4 plane escapes and obstacle-aware L1/L4 signal routing.

No footprints, net assignments, clearances, L2 or L3 zone outlines are changed.
The explicit QFN engineering option adds a scoped power-width exception only.
Every candidate is refilled and accepted only after native KiCad 8 DRC shows
zero violations/warnings and strictly fewer airwires. This is an engineering
router, not a signal-integrity or manufacturing-release certification.
"""
from __future__ import annotations
import argparse
from collections import Counter
import heapq
import itertools
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import time

import numpy as np
import pcbnew
from shapely import contains_xy, prepare
from shapely.geometry import Point, LineString, box
from shapely.ops import unary_union

POWER = {'3V3A', '3V3D', '5V_ISO', 'VREG_1V1'}
LAYERS = (pcbnew.F_Cu, pcbnew.B_Cu)
PROJECT_SNAPSHOTS = {}


def xy(point):
    return (pcbnew.ToMM(point.x), pcbnew.ToMM(point.y))


def vector(point):
    return pcbnew.VECTOR2I(*(pcbnew.FromMM(float(n)) for n in point))


def metrics(report):
    return {'violations': len(report['violations']),
            'warnings': sum(i['severity'] == 'warning' for i in report['violations'] + report['unconnected_items']),
            'unconnected': len(report['unconnected_items'])}


def native(board_path, report_path, refill=True):
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
    result = subprocess.run(cmd, capture_output=True, text=True)
    project.write_text(PROJECT_SNAPSHOTS[key])
    if result.returncode not in (0, 5) or not report_path.exists():
        raise RuntimeError(f'Native DRC failed: {result.returncode}: {result.stdout} {result.stderr}')
    report = json.loads(report_path.read_text())
    if not report.get('kicad_version', '').startswith('8.'):
        raise RuntimeError('Native KiCad 8 required')
    return report


def net_of(airwire):
    names = {re.search(r'\[([^]]+)\]', i['description']).group(1)
             for i in airwire['items'] if '[' in i['description']}
    if len(names) != 1:
        raise RuntimeError('Ambiguous native airwire net')
    return next(iter(names))


def objects(board):
    return {i.m_Uuid.AsString(): i for i in itertools.chain(
        board.GetTracks(), (p for f in board.GetFootprints() for p in f.Pads()))}


def points(item):
    if isinstance(item, pcbnew.PCB_TRACK) and not isinstance(item, pcbnew.PCB_VIA):
        start, end = xy(item.GetStart()), xy(item.GetEnd())
        # Existing trunks can be branched along their length, not only at ends.
        # Sampling keeps the search bounded; native connectivity validates taps.
        steps = min(20, max(1, math.ceil(math.dist(start, end)/2)))
        return [(start[0]+(end[0]-start[0])*i/steps,
                 start[1]+(end[1]-start[1])*i/steps) for i in range(steps+1)]
    return [xy(item.GetPosition())]


def connected_anchors(board, item):
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


def make_track(board, start, end, net, width, layer):
    if math.dist(start, end) < .001:
        return
    track = pcbnew.PCB_TRACK(board)
    track.SetStart(vector(start)); track.SetEnd(vector(end))
    track.SetWidth(pcbnew.FromMM(width)); track.SetLayer(layer); track.SetNetCode(net)
    board.Add(track)


def make_via(board, point, net, diameter=.65):
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(vector(point)); via.SetWidth(pcbnew.FromMM(diameter))
    via.SetDrill(pcbnew.FromMM(.30)); via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); via.SetNetCode(net)
    board.Add(via)


def obstacles(board, net, width, clearance, window):
    """Conservative pad boxes; exact buffered track/via obstacles.

    Native DRC is authoritative for rotated/custom pads, holes, arcs and zones.
    Pad boxes overestimate rotated-pad outlines rather than underestimating them.
    """
    by_layer = [[], []]
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            if pad.GetNetCode() == net:
                continue
            bounds = pad.GetBoundingBox()
            shape = box(pcbnew.ToMM(bounds.GetX()), pcbnew.ToMM(bounds.GetY()),
                        pcbnew.ToMM(bounds.GetRight()), pcbnew.ToMM(bounds.GetBottom()))
            if not shape.intersects(window):
                continue
            for index, layer in enumerate(LAYERS):
                if pad.IsOnLayer(layer):
                    by_layer[index].append(shape.buffer(clearance + width / 2 + .005))
    via_obstacles = []
    for track in board.GetTracks():
        if isinstance(track, pcbnew.PCB_VIA):
            # Same-net copper may overlap, but drilled holes still need spacing.
            via_obstacles.append(Point(xy(track.GetPosition())).buffer(
                pcbnew.ToMM(track.GetDrillValue()) / 2 + .15 + .255))
        if track.GetNetCode() == net:
            continue
        radius = pcbnew.ToMM(track.GetWidth()) / 2
        if isinstance(track, pcbnew.PCB_VIA):
            shape = Point(xy(track.GetPosition())).buffer(radius)
            indices = [0, 1]
        elif isinstance(track, pcbnew.PCB_ARC):
            bounds = track.GetBoundingBox()
            shape = box(pcbnew.ToMM(bounds.GetX()), pcbnew.ToMM(bounds.GetY()),
                        pcbnew.ToMM(bounds.GetRight()), pcbnew.ToMM(bounds.GetBottom()))
            indices = [i for i, layer in enumerate(LAYERS) if track.GetLayer() == layer]
        else:
            shape = LineString([xy(track.GetStart()), xy(track.GetEnd())]).buffer(radius)
            indices = [i for i, layer in enumerate(LAYERS) if track.GetLayer() == layer]
        if not shape.intersects(window):
            continue
        for index in indices:
            by_layer[index].append(shape.buffer(clearance + width / 2 + .005))
        if indices:
            via_obstacles.append(shape.buffer(clearance + .325 + .005))
    # No via-in-pad: keep every component pad body clear, including same-net pads.
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            b = pad.GetBoundingBox()
            shape = box(pcbnew.ToMM(b.GetX()), pcbnew.ToMM(b.GetY()),
                        pcbnew.ToMM(b.GetRight()), pcbnew.ToMM(b.GetBottom()))
            if shape.intersects(window):
                via_obstacles.append(shape.buffer(.325 + clearance + .005))
    return [unary_union(shapes) for shapes in by_layer], unary_union(via_obstacles)


def search(board, start, goal, net, width, clearance, both_layers, margin, step=.1, max_nodes=180000,
           deadline=float('inf'), start_layer=0, goal_layer=0, reserved_bottom=None):
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
    shapes, via_shape = obstacles(board, net, width, clearance, window)
    if reserved_bottom is not None:
        shapes[1] = unary_union([shapes[1], reserved_bottom.buffer(width/2+clearance+.005)])
        via_shape = unary_union([via_shape, reserved_bottom.buffer(.325+clearance+.005)])
    for shape in (*shapes, via_shape):
        prepare(shape)
    gx, gy = np.meshgrid(xx, yy)
    blocked = [contains_xy(shape, gx, gy) for shape in shapes]
    via_blocked = contains_xy(via_shape, gx, gy)
    via_edge = .325 + .25 + .105
    via_blocked |= ((gx < pcbnew.ToMM(bounds.GetX()) + via_edge)
                    | (gx > pcbnew.ToMM(bounds.GetRight()) - via_edge)
                    | (gy < pcbnew.ToMM(bounds.GetY()) + via_edge)
                    | (gy > pcbnew.ToMM(bounds.GetBottom()) - via_edge))
    def pos(n): return (float(xx[n[1]]), float(yy[n[2]]))
    def anchors(point, layer):
        ix = int(round((point[0] - x0) / step)); iy = int(round((point[1] - y0) / step))
        result = []
        for dx, dy in itertools.product(range(-2, 3), repeat=2):
            x, y = ix + dx, iy + dy
            if 0 <= x < len(xx) and 0 <= y < len(yy) and not blocked[layer][y, x]:
                n = (layer, x, y)
                line = LineString([point, pos(n)])
                if not line.intersects(shapes[layer]): result.append(n)
        return result
    starts, goals = anchors(start, start_layer), set(anchors(goal, goal_layer))
    if not starts or not goals:
        return None
    def heuristic(n):
        p = pos(n)
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
        if n in goals:
            path = []
            while n is not None:
                path.append((n[0], *pos(n))); n = previous[n]
            path.reverse()
            return [(start_layer, *start)] + path + [(goal_layer, *goal)]
        layer, x, y = n
        neighbors = []
        for dx, dy in moves:
            ax, ay = x + dx, y + dy
            if not (0 <= ax < len(xx) and 0 <= ay < len(yy)) or blocked[layer][ay, ax]: continue
            if dx and dy and (blocked[layer][y, ax] or blocked[layer][ay, x]): continue
            m = (layer, ax, ay)
            preferred = (dy == 0 if layer == 0 else dx == 0)
            neighbors.append((m, step * math.hypot(dx, dy) * (1 if preferred else 1.2)))
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


def add_path(board, path, net, width):
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
            if point not in vias: make_via(board, point, net); vias.add(point)
        else:
            make_track(board, a[1:], b[1:], net, width, LAYERS[a[0]])
    return len(vias)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--board', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--seconds', type=int, default=600)
    p.add_argument('--mode', choices=['planes', 'signals', 'all'], default='all')
    p.add_argument('--candidate-offset',type=int,default=0,
                   help='Rotate equally prioritized candidates between isolated worker slices')
    p.add_argument('--allow-bottom-analog', action='store_true',
                   help='Engineering experiment only; final return-path/SI review still required')
    p.add_argument('--qfn-power-neckdown', action='store_true',
                   help='Engineering-only U23 power necks: 0.15 mm width, <=0.8 mm length; no clearance relaxation')
    p.add_argument('--max-routes', type=int, default=1000)
    p.add_argument('--connection-seconds', type=float, default=10,
                   help='Bound search time per connection so one blocked pin cannot starve the bus')
    a = p.parse_args()
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
    report = native(working, a.output_dir/'drc-initial.json')
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
            plane = net in POWER | {'AGND'} and net != 'VREG_1V1'
            if a.mode == 'planes' and not plane or a.mode == 'signals' and plane: continue
            endpoints = [indexed.get(i['uuid']) for i in airwire['items']]
            if any(i is None for i in endpoints): continue
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
                escape_targets = []
                for endpoint in endpoints:
                    if not isinstance(endpoint, pcbnew.PAD): continue
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
                    if a.qfn_power_neckdown and net == '3V3D' and footprint.GetReference() == 'U23':
                        center = xy(footprint.GetPosition())
                        dx, dy = start[0]-center[0], start[1]-center[1]
                        normal = ((math.copysign(1, dx), 0) if abs(dx) > abs(dy)
                                  else (0, math.copysign(1, dy)))
                        exit_point = (start[0]+.8*normal[0], start[1]+.8*normal[1])
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
                            if math.dist(start,goal)>10: continue
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
                        exit_point = (point[0]+.8*normal[0], point[1]+.8*normal[1])
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
                    pairs=heapq.nsmallest(12,itertools.product(
                        connected_anchors(board,endpoints[0]),connected_anchors(board,endpoints[1])),
                        key=lambda pair:math.dist(pair[0][1:],pair[1][1:]))
                for anchor_start,anchor_goal in pairs:
                    start,goal=anchor_start[1:],anchor_goal[1:]
                    if analog and not a.allow_bottom_analog and (anchor_start[0] or anchor_goal[0]): continue
                    for margin in (2., 6., 12.):
                        signature = (net, anchor_start, anchor_goal, margin)
                        if signature in tried: continue
                        tried.add(signature)
                        path = search(board, start, goal, code, width, clearance,
                                      not analog or a.allow_bottom_analog, margin,
                                      deadline=min(search_deadline,time.monotonic()+2),
                                      start_layer=anchor_start[0], goal_layer=anchor_goal[0])
                        if path:
                            proposals.append(('path', path)); break
                        if time.monotonic() >= search_deadline: break
                    if proposals or time.monotonic() >= search_deadline: break
            for proposal in proposals:
                signature = (net, repr(proposal))
                if signature in tried: continue
                tried.add(signature)
                candidate = pcbnew.LoadBoard(str(accepted))
                if proposal[0] == 'thermal-ep57':
                    make_via(candidate, proposal[1], code)
                elif proposal[0] == 'escape':
                    if proposal[1] in necks:
                        make_track(candidate, necks[proposal[1]], proposal[1], code, .15, pcbnew.F_Cu)
                    make_track(candidate, proposal[1], proposal[2], code, width, pcbnew.F_Cu)
                    make_via(candidate, proposal[2], code)
                else:
                    path_start = tuple(proposal[1][0][1:])
                    if path_start in necks:
                        make_track(candidate, necks[path_start], path_start, code, .15, pcbnew.F_Cu)
                    path_end = tuple(proposal[1][-1][1:])
                    if path_end in necks:
                        make_track(candidate, necks[path_end], path_end, code, .15, pcbnew.F_Cu)
                    add_path(candidate, proposal[1], code, width)
                    if proposal[0] == 'escape-path': make_via(candidate, proposal[2], code)
                pcbnew.SaveBoard(str(working), candidate)
                count += 1
                candidate_report = native(working, a.output_dir/'drc-candidate.json')
                m = metrics(candidate_report)
                valid = not m['violations'] and not m['warnings'] and m['unconnected'] < len(report['unconnected_items'])
                event = {'attempt': count, 'net': net, 'kind': proposal[0], 'accepted': valid, **m}
                history.append(event); print(json.dumps(event), flush=True)
                (a.output_dir/'history.json').write_text(json.dumps(history, indent=2)+'\n')
                if valid:
                    shutil.copy2(working, accepted); report = candidate_report
                    shutil.copy2(a.output_dir/'drc-candidate.json', a.output_dir/'drc-accepted.json')
                    improved = True
                    break
                if time.monotonic() >= deadline or count >= a.max_routes: break
            if improved or time.monotonic() >= deadline or count >= a.max_routes: break
        if not improved: break
    shutil.copy2(accepted, working)
    final = native(working, a.output_dir/'drc-final.json')
    result = {'native_kicad_version': final['kicad_version'], **metrics(final),
              'allow_bottom_analog': a.allow_bottom_analog,
              'qfn_power_neckdown': 'Engineering U23 local power escape neck' in working.with_suffix('.kicad_dru').read_text(),
              'engineering_only': True, 'release_authorized': False, 'history': history}
    (a.output_dir/'closure-result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k != 'history'}, indent=2))


if __name__ == '__main__':
    main()
