#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Extract actual EP vias, QSPI layer paths and native closure evidence."""
from __future__ import annotations

import argparse,json
from pathlib import Path
import route_targeted_closure as r
from route_rp2040_escape import QSPI

def main() -> None:
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--board',type=Path,required=True)
 p.add_argument('--drc',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 b=r.pcbnew.LoadBoard(str(a.board));f=next(f for f in b.GetFootprints() if f.GetReference()=='U23')
 ep=next(p for p in f.Pads() if p.GetNumber()=='57');center=r.xy(ep.GetPosition());size=r.xy(ep.GetSize())
 area=r.box(center[0]-size[0]/2,center[1]-size[1]/2,center[0]+size[0]/2,center[1]+size[1]/2)
 ground=[];bus={name:{'length_mm':{'F.Cu':0.,'B.Cu':0.},'vias':[],'segments':[]} for name in sorted(QSPI)};conflicts=[]
 for t in b.GetTracks():
  net=t.GetNetname()
  if isinstance(t,r.pcbnew.PCB_VIA):
   pos=r.xy(t.GetPosition())
   if t.GetNetCode()==ep.GetNetCode() and area.contains(r.Point(pos)):
    ground.append({'uuid':t.m_Uuid.AsString(),'position_mm':pos,'diameter_mm':r.pcbnew.ToMM(t.GetWidth()),
                   'drill_mm':r.pcbnew.ToMM(t.GetDrillValue()),'layer_span':['F.Cu','B.Cu'],
                   'L2_AGND_contact':any(z.GetNetCode()==ep.GetNetCode() and z.IsOnLayer(r.pcbnew.In1_Cu)
                                         and z.HitTestFilledArea(r.pcbnew.In1_Cu,t.GetPosition()) for z in b.Zones())})
   if net in QSPI:bus[net]['vias'].append({'uuid':t.m_Uuid.AsString(),'position_mm':pos})
  elif net in QSPI:
   start,end=r.xy(t.GetStart()),r.xy(t.GetEnd());layer=b.GetLayerName(t.GetLayer())
   if layer not in bus[net]['length_mm']:raise RuntimeError('Unexpected QSPI inner layer')
   bus[net]['length_mm'][layer]+=r.math.dist(start,end)
   bus[net]['segments'].append({'uuid':t.m_Uuid.AsString(),'layer':layer,'start_mm':start,'end_mm':end,'width_mm':r.pcbnew.ToMM(t.GetWidth())})
   if layer=='B.Cu' and r.LineString([start,end]).buffer(r.pcbnew.ToMM(t.GetWidth())/2).intersects(area):
    conflicts.append({'net':net,'uuid':t.m_Uuid.AsString()})
 report=json.loads(a.drc.read_text())
 ep_air=[i for i in report['unconnected_items'] if any('Pad 57 ' in v['description'] and 'U23 ' in v['description'] for v in i['items'])]
 qspi_air=[i for i in report['unconnected_items'] if r.net_of(i) in QSPI]
 result={'native_kicad_version':report['kicad_version'],'ep_center_mm':center,'ep_size_mm':size,'ground_vias':ground,
         'ep_has_direct_L2_AGND_contact':any(v['L2_AGND_contact'] for v in ground),
         'native_EP_related_airwires':len(ep_air),'native_QSPI_airwires':len(qspi_air),
         'bottom_EP_corridor_completely_clear':not conflicts,'remaining_QSPI_under_EP':conflicts,
         'QSPI_SCLK_native_alias':'QSPI_CLK','qspi':bus,
         'length_note':'Copper centerline totals, not a timing/skew or impedance sign-off.',
         'routing_completed':False,'fabrication_release':False,**r.metrics(report)}
 a.output.write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({k:v for k,v in result.items() if k not in ('qspi','remaining_QSPI_under_EP')},indent=2))
if __name__=='__main__':main()
