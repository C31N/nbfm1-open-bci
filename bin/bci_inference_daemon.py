# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

import argparse
from collections import deque
import os
from pathlib import Path
import socket
import struct
import time
from typing import Iterator, Optional

import numpy as np

from ring_protocol import BCI_PACKET_MAGIC, RawRingReader, parse_slot
from secure_stream import DecoderFrame, SecureFrameExporter
from trt_runtime import ORTRunner, TensorRTRunner


class OnlineNormalizer:
    def __init__(self, channels: int, alpha: float = 0.999) -> None:
        self.mean = np.zeros(channels, dtype=np.float64)
        self.var = np.ones(channels, dtype=np.float64)
        self.alpha = float(alpha)
        self.ready = False

    def __call__(self, x: np.ndarray) -> np.ndarray:
        x64 = np.asarray(x, dtype=np.float64)
        if not self.ready:
            self.mean[:] = x64
            self.var[:] = 1.0
            self.ready = True
        delta = x64 - self.mean
        self.mean = self.alpha * self.mean + (1.0 - self.alpha) * x64
        self.var = self.alpha * self.var + (1.0 - self.alpha) * (delta * delta)
        return ((x64 - self.mean) / np.sqrt(self.var + 1e-6)).astype(np.float32)


def default_geometry() -> np.ndarray:
    n = 128
    idx = np.arange(n, dtype=np.float32)
    phi = np.arccos(1.0 - 2.0 * (idx + 0.5) / n)
    theta = np.pi * (1.0 + 5.0 ** 0.5) * idx
    xyz = np.stack((np.sin(phi)*np.cos(theta), np.sin(phi)*np.sin(theta), np.cos(phi)), axis=1).astype(np.float32)
    return np.concatenate((xyz, xyz), axis=1)[None,:,:]


class SerialBridgeSource:
    FRAME_BYTES=168
    MAGIC=struct.pack("<I",BCI_PACKET_MAGIC)
    def __init__(self,port:str,baud:int=921600)->None:
        import serial
        self.serial=serial.Serial(port=port,baudrate=baud,timeout=0.05)
        self.buf=bytearray()
    def packets(self)->Iterator[tuple]:
        while True:
            chunk=self.serial.read(4096)
            if chunk:self.buf.extend(chunk)
            while True:
                pos=self.buf.find(self.MAGIC)
                if pos<0:
                    if len(self.buf)>3:del self.buf[:-3]
                    break
                if pos:del self.buf[:pos]
                if len(self.buf)<self.FRAME_BYTES:break
                frame=bytes(self.buf[:self.FRAME_BYTES])
                try:pkt=parse_slot(frame)
                except ValueError:
                    del self.buf[0];continue
                del self.buf[:self.FRAME_BYTES]
                yield pkt,time.time_ns()


class RingSource:
    def __init__(self,path:str)->None:self.reader=RawRingReader(path)
    def packets(self)->Iterator[tuple]:
        while True:
            slot=self.reader.pop(timeout_s=0.2)
            if slot is None:continue
            try:pkt=parse_slot(slot)
            except ValueError:continue
            yield pkt,pkt.timestamp_ns


def detect_serial(explicit:str)->Optional[str]:
    if explicit:return explicit if os.path.exists(explicit) else None
    if os.path.exists("/dev/bci-esp32"):return "/dev/bci-esp32"
    try:
        from serial.tools import list_ports
        for port in list_ports.comports():
            desc=" ".join(str(x or "") for x in (port.description,port.manufacturer,port.product)).lower()
            if port.vid==0x303A or "espressif" in desc or "esp32" in desc:return port.device
    except Exception:pass
    return None


class SecureSocketClient:
    def __init__(self,path:str)->None:self.path=path;self.sock:Optional[socket.socket]=None
    def _connect(self)->bool:
        if self.sock is not None:return True
        s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);s.settimeout(0.25)
        try:s.connect(self.path)
        except OSError:s.close();return False
        self.sock=s;return True
    def send(self,frame:bytes)->bool:
        if not self._connect():return False
        try:
            assert self.sock is not None
            self.sock.sendall(struct.pack("<I",len(frame))+frame);return True
        except OSError:
            if self.sock is not None:self.sock.close()
            self.sock=None;return False


def load_key(path:str)->bytes:
    raw=Path(path).read_bytes()
    if len(raw)!=32:raise RuntimeError("master key must be 32 bytes")
    return raw


def main()->None:
    p=argparse.ArgumentParser()
    p.add_argument("--ring",default="/dev/shm/bci/raw-ring")
    p.add_argument("--source",choices=("auto","ring","serial"),default="auto")
    p.add_argument("--serial",default="")
    p.add_argument("--serial-baud",type=int,default=921600)
    p.add_argument("--engine",default="/opt/bci-stack/models/nbfm1_fp16.engine")
    p.add_argument("--onnx",default="/opt/bci-stack/models/nbfm1.onnx")
    p.add_argument("--cache",default="/opt/bci-stack/engine-cache")
    p.add_argument("--socket",default="/run/bci/secure.sock")
    p.add_argument("--key-file",default="/run/bci/master.key")
    p.add_argument("--fast-samples",type=int,default=512)
    p.add_argument("--fnirs-samples",type=int,default=20)
    p.add_argument("--hop-samples",type=int,default=16)
    p.add_argument("--intent-threshold",type=float,default=0.95)
    p.add_argument("--force-ort",action="store_true")
    args=p.parse_args()

    serial_port=detect_serial(args.serial) if args.source in ("auto","serial") else None
    if args.source=="serial" and not serial_port:raise SystemExit("serial source requested but no ESP32 found")
    if serial_port:
        source=SerialBridgeSource(serial_port,args.serial_baud);source_mode="serial";upsample=4
    else:
        while not os.path.exists(args.ring):time.sleep(0.05)
        source=RingSource(args.ring);source_mode="ring";upsample=1

    if not args.force_ort and os.path.exists(args.engine):
        try:runtime=TensorRTRunner(args.engine);runtime_name="tensorrt"
        except Exception as exc:
            print(f"TensorRT unavailable ({exc}); using ONNX Runtime",flush=True)
            runtime=ORTRunner(args.onnx,args.cache);runtime_name="onnxruntime"
    else:
        runtime=ORTRunner(args.onnx,args.cache);runtime_name="onnxruntime"
    print(f"BCI inference source={source_mode} runtime={runtime_name}",flush=True)

    exporter=SecureFrameExporter(load_key(args.key_file),args.intent_threshold)
    out=SecureSocketClient(args.socket)
    geometry=default_geometry()
    eeg_norm=OnlineNormalizer(128);meg_norm=OnlineNormalizer(128);fnirs_norm=OnlineNormalizer(320,alpha=0.995)
    eeg_window=deque(maxlen=args.fast_samples);meg_window=deque(maxlen=args.fast_samples);fnirs_window=deque(maxlen=args.fnirs_samples)
    for _ in range(args.fnirs_samples):fnirs_window.append(np.zeros(320,dtype=np.float32))
    sample_counter=0

    try:
        for pkt,latency_timestamp in source.packets():
            if source_mode=="serial":
                raw_eeg=np.zeros(128,dtype=np.float32);raw_eeg[:8]=(pkt.eeg[:8]-2048.0)/2048.0
                raw_meg=np.zeros(128,dtype=np.float32)
            else:
                raw_eeg=pkt.eeg*1.0e-3;raw_meg=pkt.meg
            eeg_s=eeg_norm(raw_eeg);meg_s=meg_norm(raw_meg)
            for _ in range(upsample):
                eeg_window.append(eeg_s.copy());meg_window.append(meg_s.copy());sample_counter+=1
            if pkt.fnirs_long is not None and pkt.fnirs_short is not None:
                f=np.concatenate((pkt.fnirs_long.reshape(-1),pkt.fnirs_short.reshape(-1))).astype(np.float32)
                fnirs_window.append(fnirs_norm(np.log(np.maximum(f,1.0))))
            if len(eeg_window)<args.fast_samples or sample_counter<args.hop_samples:continue
            sample_counter=0
            eeg=np.stack(eeg_window,axis=0).T[None,:,:].astype(np.float32,copy=False)
            meg=np.stack(meg_window,axis=0).T[None,:,:].astype(np.float32,copy=False)
            fnirs=np.stack(fnirs_window,axis=0).T[None,:,:].astype(np.float32,copy=False)
            outputs=runtime.infer({"eeg":eeg,"meg":meg,"meg_geometry":geometry,"fnirs":fnirs})
            mm=np.asarray(outputs["motor_mean"],dtype=np.float32).reshape(1,4)[0]
            ms=np.asarray(outputs["motor_log_std"],dtype=np.float32).reshape(1,4)[0]
            il=float(np.asarray(outputs["intent_logit"]).reshape(-1)[0])
            ip=1.0/(1.0+np.exp(-np.clip(il,-30.0,30.0)))
            speech=np.asarray(outputs["speech_ctc_logits"],dtype=np.float32)
            if speech.ndim==3:speech=speech[0]
            encrypted=exporter.encrypt_frame(DecoderFrame(latency_timestamp,float(ip),mm,ms,speech))
            out.send(encrypted)
    finally:
        runtime.close()

if __name__=="__main__":main()
