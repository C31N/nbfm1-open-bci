#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Read-only, deterministic B.Cu/In2.Cu component-transition graph.

Only copper-safe overlapping component areas of both layers that ALSO belong
to the 0.505 mm power-excluded via-centre region can form graph edges.
Disconnected results are local to the already clipped search window. This
graph never changes a board, qualifies DRC or authorizes fabrication.
"""
from __future__ import annotations

from collections import deque
from typing import Any


def transition_graph(
    bcu_free: Any, in2_free: Any, via_free: Any,
    source: tuple[float, float], target: tuple[float, float],
) -> dict[str, Any]:
    from shapely.geometry import Point
    from shapely.ops import nearest_points
    from shapely.strtree import STRtree
    from escape_mesh_505 import polygons
    from probe_ch022_bcu_in2_bypass import _via_centres

    bs = polygons(bcu_free)
    ins = polygons(in2_free)
    from_pt = Point(source)
    to_pt = Point(target)
    roots = [idx for idx, shape in enumerate(bs) if shape.covers(from_pt)]
    ends = [idx for idx, shape in enumerate(bs) if shape.covers(to_pt)]
    graph: dict[str, Any] = {
        'status': 'no_anchor_component', 'read_only': True,
        'accepted': False, 'routing_completed': False,
        'fabrication_release': False,
        'BCu_component_count': len(bs), 'In2_component_count': len(ins),
        'source_BCu_component': roots[0] if roots else None,
        'target_BCu_component': ends[0] if ends else None,
        'valid_via_transition_edges': 0, 'sampled_via_centres': 0,
        'multihop_connected': False, 'minimum_layer_transitions': None,
        'component_path': [], 'transition_via_centres_mm': [],
        'source_reachable_In2_components': [],
        'target_reachable_In2_components': [],
        'closest_disconnected_In2_gap_mm': None,
        'nearby_disconnected_In2_component_pair': None,
        'closest_disconnected_In2_gap_edges_mm': None,
    }
    if not roots or not ends or not ins:
        return graph
    # Node layer prefix: B.Cu ('B', i), In2.Cu ('I', j).
    adj: dict[tuple[str, int], list[tuple[str, int]]] = {}
    contacts: dict[tuple[int, int], list[tuple[float, float]]] = {}
    tree = STRtree(ins)
    for bidx, bp in enumerate(bs):
        eligible_b = bp.intersection(via_free)
        if eligible_b.area < 1e-10:
            continue
        for candidate in tree.query(eligible_b):
            idx = int(candidate)
            inter = eligible_b.intersection(ins[idx]).buffer(-.000005)
            if inter.area <= 1e-10:
                continue
            centres = _via_centres(inter, 3)
            if not centres:
                continue
            bn, inn = ('B', bidx), ('I', idx)
            adj.setdefault(bn, []).append(inn)
            adj.setdefault(inn, []).append(bn)
            contacts[(bidx, idx)] = centres
    graph['valid_via_transition_edges'] = len(contacts)
    graph['sampled_via_centres'] = sum(len(v) for v in contacts.values())

    def search(root: tuple[str, int]):
        frontier = deque([root])
        prev: dict[tuple[str, int], tuple[str, int] | None] = {root: None}
        while frontier:
            node = frontier.popleft()
            for nxt in sorted(adj.get(node, [])):
                if nxt in prev:
                    continue
                prev[nxt] = node
                frontier.append(nxt)
        return prev

    first = ('B', roots[0])
    last = ('B', ends[0])
    from_reach = search(first)
    to_reach = search(last)
    si = sorted(n[1] for n in from_reach if n[0] == 'I')
    ti = sorted(n[1] for n in to_reach if n[0] == 'I')
    graph['source_reachable_In2_components'] = si
    graph['target_reachable_In2_components'] = ti
    if last in from_reach:
        path: list[tuple[str, int]] = []
        node: tuple[str, int] | None = last
        while node is not None:
            path.append(node)
            node = from_reach[node]
        path.reverse()
        graph['status'] = 'multihop_component_path_found_unqualified'
        graph['multihop_connected'] = True
        graph['minimum_layer_transitions'] = len(path) - 1
        graph['component_path'] = [f'{l}:{idx}' for l, idx in path]
        graph['transition_via_centres_mm'] = [
            list(contacts[(a[1], b[1])][0]
                 if a[0] == 'B' else contacts[(b[1], a[1])][0])
            for a, b in zip(path, path[1:])
        ]
        return graph

    graph['status'] = 'separate_BCu_In2_component_graphs'
    if si and ti:
        closest = None
        for a in si:
            for b in ti:
                if a == b:
                    continue
                dist = ins[a].distance(ins[b])
                if closest is None or (dist, a, b) < closest[:3]:
                    closest = (dist, a, b)
        if closest is not None:
            distance, a, b = closest
            x, y = nearest_points(ins[a], ins[b])
            graph['closest_disconnected_In2_gap_mm'] = round(distance, 7)
            graph['nearby_disconnected_In2_component_pair'] = [a, b]
            graph['closest_disconnected_In2_gap_edges_mm'] = [
                [round(x.x, 6), round(x.y, 6)],
                [round(y.x, 6), round(y.y, 6)],
            ]
    return graph
