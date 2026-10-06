#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Report real filled islands and same-net plated-via contacts, KiCad 8.

A via contact proves a layer transition, not whole-board connectivity. Native
DRC remains authoritative. No zone is connected to a differently named plane.
"""
import argparse,json
from pathlib import Path
import pcbnew

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--board',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
 a=p.parse_args();b=pcbnew.LoadBoard(str(a.board));rows=[]
 vias=[t for t in b.GetTracks() if isinstance(t,pcbnew.PCB_VIA)]
 for z in b.Zones():
  for layer in z.GetLayerSet().Seq():
   polygons=z.GetFilledPolysList(layer)
   for index in range(polygons.OutlineCount()):
    contacts=[v for v in vias if v.GetNetCode()==z.GetNetCode() and v.IsOnLayer(layer)
              and polygons.Contains(v.GetPosition(),index)]
    rows.append({'zone_uuid':z.m_Uuid.AsString(),'net':z.GetNetname(),'layer':b.GetLayerName(layer),
                 'filled_island':index,'same_net_through_vias':len(contacts),
                 'via_uuids':[v.m_Uuid.AsString() for v in contacts],
                 'pad_connection_mode':int(z.GetPadConnection()),
                 'thermal_gap_mm':pcbnew.ToMM(z.GetThermalReliefGap()),
                 'thermal_spoke_mm':pcbnew.ToMM(z.GetThermalReliefSpokeWidth())})
 result={'native_kicad_version':pcbnew.GetBuildVersion(),'board':str(a.board),'islands':rows,
         'islands_without_via_contact':sum(row['same_net_through_vias']==0 for row in rows),
         'whole_board_connectivity_proven':False,'connectivity_authority':'native pcb drc, including unconnected_items'}
 a.output.write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({k:v for k,v in result.items() if k!='islands'},indent=2))
if __name__=='__main__':main()
