# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations
from dataclasses import dataclass
import mmap, os, struct, time
from pathlib import Path
import numpy as np

PAGE_BYTES=4096
MAGIC=b"BCITEL1\0"
STATE_TO_CODE={"LOCKED":0,"ARMED":1,"DECODING":2}
CODE_TO_STATE={v:k for k,v in STATE_TO_CODE.items()}
PREFIX_STRUCT=struct.Struct("<8sQ")
BODY_STRUCT=struct.Struct("<QfffB3x4f4fQQ")

@dataclass(frozen=True)
class Telemetry:
    timestamp_ns:int
    latency_ms:float
    p99_ms:float
    intent_probability:float
    state:str
    motor:np.ndarray
    motor_std:np.ndarray
    frame_sequence:int
    trigger_count:int

class _MappedTelemetry:
    def __init__(self,path:str,create:bool)->None:
        self.path=Path(path)
        if create:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            fd=os.open(self.path,os.O_RDWR|os.O_CREAT,0o600)
            try:
                os.ftruncate(fd,PAGE_BYTES); self.mm=mmap.mmap(fd,PAGE_BYTES,access=mmap.ACCESS_WRITE)
            finally: os.close(fd)
            os.chmod(self.path,0o600)
            if self.mm[:8]!=MAGIC:
                self.mm[:]=b"\0"*PAGE_BYTES; PREFIX_STRUCT.pack_into(self.mm,0,MAGIC,0)
        else:
            fd=os.open(self.path,os.O_RDONLY)
            try:self.mm=mmap.mmap(fd,PAGE_BYTES,access=mmap.ACCESS_READ)
            finally:os.close(fd)
    def close(self)->None:self.mm.close()

class TelemetryWriter(_MappedTelemetry):
    def __init__(self,path:str)->None:super().__init__(path,True)
    def write(self,item:Telemetry)->None:
        magic,seq=PREFIX_STRUCT.unpack_from(self.mm,0)
        if magic!=MAGIC:raise RuntimeError("telemetry magic changed")
        if seq & 1:seq+=1
        struct.pack_into("<Q",self.mm,8,seq+1)
        motor=np.asarray(item.motor,dtype=np.float32).reshape(4)
        std=np.asarray(item.motor_std,dtype=np.float32).reshape(4)
        BODY_STRUCT.pack_into(self.mm,PREFIX_STRUCT.size,int(item.timestamp_ns),
            float(item.latency_ms),float(item.p99_ms),float(item.intent_probability),
            STATE_TO_CODE[item.state],*[float(x) for x in motor],*[float(x) for x in std],
            int(item.frame_sequence),int(item.trigger_count))
        struct.pack_into("<Q",self.mm,8,seq+2)

class TelemetryReader(_MappedTelemetry):
    def __init__(self,path:str)->None:super().__init__(path,False)
    def read(self,retries:int=100)->Telemetry:
        for _ in range(retries):
            magic1,seq1=PREFIX_STRUCT.unpack_from(self.mm,0)
            if magic1!=MAGIC:raise RuntimeError("invalid telemetry magic")
            if seq1 & 1:time.sleep(0);continue
            f=BODY_STRUCT.unpack_from(self.mm,PREFIX_STRUCT.size)
            magic2,seq2=PREFIX_STRUCT.unpack_from(self.mm,0)
            if magic1==magic2 and seq1==seq2 and not(seq2&1):
                ts,lat,p99,p,state,*rest=f
                return Telemetry(ts,lat,p99,p,CODE_TO_STATE.get(state,"UNKNOWN"),
                    np.array(rest[:4],dtype=np.float32),np.array(rest[4:8],dtype=np.float32),
                    int(rest[8]),int(rest[9]))
        raise RuntimeError("unstable telemetry snapshot")
