# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations
import json
from pathlib import Path

class ActionRouter:
    def __init__(self,config_path:str)->None:
        self.config=json.loads(Path(config_path).read_text("utf-8"))
        self.actions=self.config["actions"]
        self.aliases={self._norm(k):v for k,v in self.config.get("aliases",{}).items()}
        self.fallback=self.config.get("fallback","noop")
    @staticmethod
    def _norm(text:str)->str:
        return " ".join(text.lower().strip().split())
    def resolve(self,text:str)->dict:
        action_id=self.aliases.get(self._norm(text),self.fallback)
        if action_id not in self.actions:action_id=self.fallback
        return {"id":action_id,**self.actions[action_id]}

def greedy_ctc(logits,vocabulary,blank_id:int=0)->str:
    import numpy as np
    ids=np.argmax(logits,axis=-1).tolist()
    out=[]; prev=None
    for i in ids:
        if i!=prev and i!=blank_id and 0<=i<len(vocabulary):out.append(vocabulary[i])
        prev=i
    return " ".join(out)
