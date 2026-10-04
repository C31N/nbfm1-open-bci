# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

from dataclasses import dataclass
import mmap
import os
from pathlib import Path
import struct
import time
from typing import Optional

import numpy as np

BCI_PACKET_MAGIC = 0x31494342
BCI_PROTOCOL_VERSION = 0x0100
BCI_DMA_SLOT_BYTES = 4096
BCI_HEADER_BYTES = 128
BCI_EEG_CHANNELS = 128
BCI_MEG_CHANNELS = 128
BCI_FNIRS_LONG_CHANNELS = 128
BCI_FNIRS_SHORT_CHANNELS = 32
BCI_FNIRS_WAVELENGTHS = 2
BCI_FAST_PACKET_BYTES = 1152
BCI_FULL_PACKET_BYTES = 2456

BCI_FLAG_EEG_PRESENT = 1 << 0
BCI_FLAG_MEG_PRESENT = 1 << 1
BCI_FLAG_FNIRS_PRESENT = 1 << 2
BCI_FLAG_TIMESTAMP_VALID = 1 << 3
BCI_FLAG_CALIBRATED = 1 << 5
BCI_FLAG_BRIDGE_PAYLOAD = 1 << 15

BCI_SAMPLE_S32_LE = 1
BCI_FNIRS_U32_INTENSITY_LE = 1

HEADER_STRUCT = struct.Struct("<IHHIIQII" "4I4I" "HHHH" "BBH" "44s" "II")
FNIRS_HEADER_STRUCT = struct.Struct("<QIHHBBHI")
BRIDGE_PAYLOAD_STRUCT = struct.Struct("<8iII")

RING_MAGIC = b"BCIRING1"
RING_VERSION = 1
RING_CONTROL_BYTES = 4096
RING_STRUCT = struct.Struct("<8sIIIIQQQQ")
RING_PRODUCER_OFFSET = 24
RING_CONSUMER_OFFSET = 32
RING_DROPPED_OFFSET = 40

def _make_crc32c_table() -> tuple[int, ...]:
    out=[]
    for value in range(256):
        crc=value
        for _ in range(8):
            crc=(crc>>1) ^ (0x82F63B78 if crc & 1 else 0)
        out.append(crc & 0xFFFFFFFF)
    return tuple(out)

_CRC32C_TABLE=_make_crc32c_table()

def crc32c(data: bytes | bytearray | memoryview, initial: int = 0) -> int:
    crc=(~initial) & 0xFFFFFFFF
    for byte in data:
        crc=_CRC32C_TABLE[(crc ^ byte) & 0xFF] ^ (crc >> 8)
    return (~crc) & 0xFFFFFFFF

@dataclass(frozen=True)
class ParsedPacket:
    sequence:int
    timestamp_ns:int
    flags:int
    status:int
    eeg:np.ndarray
    meg:np.ndarray
    fnirs_long:Optional[np.ndarray]
    fnirs_short:Optional[np.ndarray]
    digital_bits:int=0
    bridge_sample_counter:int=0

class RawRingWriter:
    def __init__(self,path:str,slot_count:int=2048,overwrite_oldest:bool=False)->None:
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
        self.slot_count=int(slot_count); self.overwrite_oldest=overwrite_oldest
        total=RING_CONTROL_BYTES+self.slot_count*BCI_DMA_SLOT_BYTES
        fd=os.open(self.path,os.O_RDWR|os.O_CREAT,0o600)
        try:
            os.ftruncate(fd,total); self.mm=mmap.mmap(fd,total,access=mmap.ACCESS_WRITE)
        finally: os.close(fd)
        os.chmod(self.path,0o600)
        self.mm[:]=b"\0"*total
        RING_STRUCT.pack_into(self.mm,0,RING_MAGIC,RING_VERSION,self.slot_count,
                              BCI_DMA_SLOT_BYTES,0,0,0,0,time.time_ns())
    def close(self)->None:self.mm.close()
    def _counter(self,o:int)->int:return struct.unpack_from("<Q",self.mm,o)[0]
    def _set_counter(self,o:int,v:int)->None:struct.pack_into("<Q",self.mm,o,int(v))
    def push(self,slot:bytes)->bool:
        if len(slot)!=BCI_DMA_SLOT_BYTES: raise ValueError("slot must be exactly 4096 bytes")
        p=self._counter(RING_PRODUCER_OFFSET); c=self._counter(RING_CONSUMER_OFFSET)
        if p-c>=self.slot_count:
            self._set_counter(RING_DROPPED_OFFSET,self._counter(RING_DROPPED_OFFSET)+1)
            if not self.overwrite_oldest:return False
            c+=1; self._set_counter(RING_CONSUMER_OFFSET,c)
        idx=p%self.slot_count; off=RING_CONTROL_BYTES+idx*BCI_DMA_SLOT_BYTES
        self.mm[off:off+BCI_DMA_SLOT_BYTES]=slot
        self._set_counter(RING_PRODUCER_OFFSET,p+1)
        return True

class RawRingReader:
    def __init__(self,path:str)->None:
        fd=os.open(path,os.O_RDWR)
        try:
            size=os.fstat(fd).st_size; self.mm=mmap.mmap(fd,size,access=mmap.ACCESS_WRITE)
        finally: os.close(fd)
        magic,version,slots,slot_bytes,_,*_=RING_STRUCT.unpack_from(self.mm,0)
        if magic!=RING_MAGIC or version!=RING_VERSION or slot_bytes!=BCI_DMA_SLOT_BYTES:
            raise RuntimeError("invalid BCI raw ring")
        self.slot_count=slots
    def close(self)->None:self.mm.close()
    def _counter(self,o:int)->int:return struct.unpack_from("<Q",self.mm,o)[0]
    def _set_counter(self,o:int,v:int)->None:struct.pack_into("<Q",self.mm,o,int(v))
    def pop(self,timeout_s:float=0.1)->Optional[bytes]:
        deadline=time.monotonic()+timeout_s
        while True:
            p=self._counter(RING_PRODUCER_OFFSET); c=self._counter(RING_CONSUMER_OFFSET)
            if c<p:
                idx=c%self.slot_count; off=RING_CONTROL_BYTES+idx*BCI_DMA_SLOT_BYTES
                slot=bytes(self.mm[off:off+BCI_DMA_SLOT_BYTES])
                self._set_counter(RING_CONSUMER_OFFSET,c+1)
                return slot
            if time.monotonic()>=deadline:return None
            time.sleep(0.00005)

def validate_packet(slot:bytes)->tuple:
    f=HEADER_STRUCT.unpack_from(slot,0)
    magic,version,header_bytes,packet_bytes=f[:4]
    if magic!=BCI_PACKET_MAGIC or version!=BCI_PROTOCOL_VERSION or header_bytes!=128:
        raise ValueError("invalid BCI packet header")
    if crc32c(memoryview(slot)[:124])!=f[-1]: raise ValueError("header CRC32C mismatch")
    if crc32c(memoryview(slot)[128:packet_bytes])!=f[-2]: raise ValueError("payload CRC32C mismatch")
    return f

def parse_slot(slot:bytes)->ParsedPacket:
    f=validate_packet(slot)
    sequence,timestamp_ns,flags,status=f[4],f[5],f[6],f[7]
    packet_bytes=f[3]
    if flags & BCI_FLAG_BRIDGE_PAYLOAD:
        if packet_bytes!=168: raise ValueError("invalid bridge packet")
        values=BRIDGE_PAYLOAD_STRUCT.unpack_from(slot,128)
        eeg=np.zeros(128,dtype=np.float32); eeg[:8]=np.asarray(values[:8],dtype=np.float32)
        return ParsedPacket(sequence,timestamp_ns,flags,status,eeg,np.zeros(128,dtype=np.float32),
                            None,None,int(values[8]),int(values[9]))
    eeg=np.frombuffer(slot,dtype="<i4",count=128,offset=128).astype(np.float32)
    meg=np.frombuffer(slot,dtype="<i4",count=128,offset=640).astype(np.float32)
    long_frame=short_frame=None
    if flags & BCI_FLAG_FNIRS_PRESENT:
        hdr=FNIRS_HEADER_STRUCT.unpack_from(slot,1152)
        _,_,long_count,short_count,wl_count,_,_,_=hdr
        if (long_count,short_count,wl_count)!=(128,32,2): raise ValueError("unsupported fNIRS dimensions")
        off=1152+FNIRS_HEADER_STRUCT.size
        long_frame=np.frombuffer(slot,dtype="<u4",count=256,offset=off).reshape(128,2).copy()
        off+=256*4
        short_frame=np.frombuffer(slot,dtype="<u4",count=64,offset=off).reshape(32,2).copy()
    return ParsedPacket(sequence,timestamp_ns,flags,status,eeg,meg,long_frame,short_frame)

def build_packet(sequence:int,timestamp_ns:int,eeg:np.ndarray,meg:np.ndarray,
                 fnirs_long:Optional[np.ndarray]=None,fnirs_short:Optional[np.ndarray]=None,
                 fnirs_sample_index:int=0)->bytes:
    has_fnirs=fnirs_long is not None and fnirs_short is not None
    packet_bytes=BCI_FULL_PACKET_BYTES if has_fnirs else BCI_FAST_PACKET_BYTES
    flags=BCI_FLAG_EEG_PRESENT|BCI_FLAG_MEG_PRESENT|BCI_FLAG_TIMESTAMP_VALID|BCI_FLAG_CALIBRATED
    if has_fnirs: flags|=BCI_FLAG_FNIRS_PRESENT
    slot=bytearray(BCI_DMA_SLOT_BYTES)
    slot[128:640]=np.asarray(eeg,dtype="<i4").reshape(128).tobytes()
    slot[640:1152]=np.asarray(meg,dtype="<i4").reshape(128).tobytes()
    lcount=scount=wcount=0
    if has_fnirs:
        la=np.asarray(fnirs_long,dtype="<u4").reshape(128,2)
        sa=np.asarray(fnirs_short,dtype="<u4").reshape(32,2)
        FNIRS_HEADER_STRUCT.pack_into(slot,1152,timestamp_ns,fnirs_sample_index,128,32,2,
                                      BCI_FNIRS_U32_INTENSITY_LE,0,0)
        off=1152+FNIRS_HEADER_STRUCT.size
        raw=la.tobytes(); slot[off:off+len(raw)]=raw; off+=len(raw)
        raw=sa.tobytes(); slot[off:off+len(raw)]=raw
        lcount,scount,wcount=128,32,2
    mask=(0xFFFFFFFF,)*4; reserved=b"\0"*44
    args=(BCI_PACKET_MAGIC,BCI_PROTOCOL_VERSION,BCI_HEADER_BYTES,packet_bytes,
          sequence & 0xFFFFFFFF,timestamp_ns,flags,0,*mask,*mask,128,128,
          lcount,scount,wcount,BCI_SAMPLE_S32_LE,0,reserved)
    slot[:128]=HEADER_STRUCT.pack(*args,0,0)
    payload_crc=crc32c(memoryview(slot)[128:packet_bytes])
    header=bytearray(HEADER_STRUCT.pack(*args,payload_crc,0))
    struct.pack_into("<I",header,124,crc32c(header[:124]))
    slot[:128]=header
    return bytes(slot)
