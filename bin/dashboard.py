# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations
import argparse,time
from telemetry_ipc import TelemetryReader

def as_dict(t):
    return {
      "timestamp_ns":int(t.timestamp_ns),"latency_ms":float(t.latency_ms),"p99_ms":float(t.p99_ms),
      "intent_probability":float(t.intent_probability),"state":t.state,
      "motor":{"vx":float(t.motor[0]),"vy":float(t.motor[1]),"vz":float(t.motor[2]),"grip":float(t.motor[3])},
      "motor_std":{"vx":float(t.motor_std[0]),"vy":float(t.motor_std[1]),"vz":float(t.motor_std[2]),"grip":float(t.motor_std[3])},
      "frame_sequence":int(t.frame_sequence),"trigger_count":int(t.trigger_count)
    }

def terminal(path:str):
    from rich.live import Live
    from rich.table import Table
    r=TelemetryReader(path)
    def render():
        t=r.read(); table=Table(title="NBFM-1 BCI Live Telemetry")
        table.add_column("Metric");table.add_column("Value")
        table.add_row("State",t.state)
        table.add_row("P(intent)",f"{t.intent_probability:.3f}")
        table.add_row("Latency",f"{t.latency_ms:.3f} ms")
        table.add_row("P99",f"{t.p99_ms:.3f} ms")
        table.add_row("Motor",f"{t.motor.tolist()}")
        return table
    with Live(render(),refresh_per_second=10) as live:
        try:
            while True: live.update(render()); time.sleep(.1)
        except KeyboardInterrupt: pass

def web(path:str,host:str,port:int):
    from fastapi import FastAPI
    import uvicorn
    reader=TelemetryReader(path)
    app=FastAPI(title="BCI Telemetry",docs_url=None,redoc_url=None)
    @app.get("/api/telemetry")
    def telemetry():return as_dict(reader.read())
    @app.get("/")
    def root():
        return {"service":"NBFM-1 BCI telemetry","endpoint":"/api/telemetry"}
    uvicorn.run(app,host=host,port=port,access_log=False)

def main():
    p=argparse.ArgumentParser();p.add_argument("--telemetry",default="/dev/shm/bci/telemetry")
    p.add_argument("--mode",choices=["terminal","web"],default="terminal")
    p.add_argument("--host",default="127.0.0.1");p.add_argument("--port",type=int,default=8088)
    a=p.parse_args(); web(a.telemetry,a.host,a.port) if a.mode=="web" else terminal(a.telemetry)

if __name__=="__main__":main()
