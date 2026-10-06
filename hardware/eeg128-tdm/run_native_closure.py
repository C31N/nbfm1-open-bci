#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Run bounded KiCad routing workers; recover only natively verified checkpoints.

The supervisor itself never imports pcbnew. A worker crash cannot promote its
last rejected candidate. Original project netclasses are restored before a
fresh verification process; accepted board/rules are copied as one checkpoint.
"""
from __future__ import annotations

import argparse,json,shutil,subprocess,sys,time
from pathlib import Path
from typing import Any

HERE=Path(__file__).resolve().parent

def verify(board: Path, report: Path) -> dict[str, Any]:
 code=('import sys; from pathlib import Path; '
       f'sys.path.insert(0,{str(HERE)!r}); '
       'from route_targeted_closure import native; '
       f'native(Path({str(board)!r}),Path({str(report)!r}))')
 log=report.with_suffix('.log')
 with log.open('w') as stream:
  proc=subprocess.run([sys.executable,'-c',code],stdout=stream,stderr=subprocess.STDOUT)
 if proc.returncode:raise RuntimeError(f'Native verification failed; see {log}')
 data=json.loads(report.read_text())
 if data['violations']:raise RuntimeError(f'Candidate has native violations/warnings; see {report}')
 return data

def main() -> None:
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--board',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True)
 p.add_argument('--seconds',type=int,default=900);p.add_argument('--mode',choices=['all','planes','signals'],default='all')
 p.add_argument('--allow-bottom-analog',action='store_true');p.add_argument('--qfn-power-neckdown',action='store_true')
 a=p.parse_args();a.output_dir.mkdir(parents=True,exist_ok=True)
 board=a.output_dir/'eeg128-tdm.kicad_pcb'
 for ext in ('.kicad_pcb','.kicad_pro','.kicad_dru'):shutil.copy2(a.board.with_suffix(ext),board.with_suffix(ext))
 project=board.with_suffix('.kicad_pro').read_text()
 current=verify(board,a.output_dir/'drc-initial.json')
 accepted=a.output_dir/'accepted.kicad_pcb';shutil.copy2(board,accepted)
 deadline=time.monotonic()+a.seconds;events=[];epoch=0
 while len(current['unconnected_items']) and time.monotonic()<deadline-15:
  duration=min(300,max(1,int(deadline-time.monotonic()-15)))
  worker=a.output_dir/f'worker-{epoch:02d}'
  cmd=[sys.executable,str(HERE/'route_targeted_closure.py'),'--board',str(board),
       '--output-dir',str(worker),'--seconds',str(duration),'--mode',a.mode,
       '--candidate-offset',str(epoch*35)]
  if a.allow_bottom_analog:cmd.append('--allow-bottom-analog')
  if a.qfn_power_neckdown:cmd.append('--qfn-power-neckdown')
  log=a.output_dir/f'worker-{epoch:02d}.log'
  with log.open('w') as stream:
   proc=subprocess.run(cmd,stdout=stream,stderr=subprocess.STDOUT)
  checkpoint=worker/'accepted.kicad_pcb';previous=board.read_bytes();previous_rules=board.with_suffix('.kicad_dru').read_bytes()
  promoted=False;reason='Worker produced no accepted checkpoint'
  if checkpoint.exists():
   shutil.copy2(checkpoint,board);board.with_suffix('.kicad_pro').write_text(project)
   shutil.copy2(worker/'eeg128-tdm.kicad_dru',board.with_suffix('.kicad_dru'))
   try:
    report=verify(board,a.output_dir/f'drc-worker-{epoch:02d}.json')
    promoted=len(report['unconnected_items'])<=len(current['unconnected_items'])
    if promoted:
     current=report;shutil.copy2(board,accepted);reason='Fresh native verification passed'
    else:reason='Native connectivity regressed'
   except RuntimeError as exc:reason=str(exc)
   if not promoted:board.write_bytes(previous);board.with_suffix('.kicad_dru').write_bytes(previous_rules)
  event={'worker':epoch,'returncode':proc.returncode,'checkpoint_verified':promoted,
         'unconnected':len(current['unconnected_items']),'reason':reason}
  events.append(event);print(json.dumps(event),flush=True)
  (a.output_dir/'worker-history.json').write_text(json.dumps(events,indent=2)+'\n')
  epoch+=1
 board.with_suffix('.kicad_pro').write_text(project)
 final=verify(board,a.output_dir/'drc-final.json')
 result={'native_kicad_version':final['kicad_version'],'violations':0,'warnings':0,
         'unconnected':len(final['unconnected_items']),'worker_history':events,
         'engineering_only':True,'routing_completed':False,'fabrication_release':False}
 (a.output_dir/'closure-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
if __name__=='__main__':main()
