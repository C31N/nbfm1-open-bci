# SPDX-License-Identifier: AGPL-3.0-only
"""Exercise local LSL ingestion; output statistics only, no raw neural recording."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import time
from neural_ingestion import LSLIngestion, SampleRing
from neural_rust_ring import RustRing


def main() -> None:
    from pylsl import resolve_byprop
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-id',required=True)
    parser.add_argument('--channels',type=int,default=128)
    parser.add_argument('--seconds',type=float,default=10.)
    parser.add_argument('--rust-library',type=Path)
    parser.add_argument('--allow-plaintext-local-lsl',action='store_true')
    args = parser.parse_args()
    if not args.allow_plaintext_local_lsl or args.seconds <= 0:
        parser.error('Explicit trusted-domain plaintext LSL acknowledgement and positive duration required')
    streams = resolve_byprop('source_id',args.source_id,timeout=5.)
    if len(streams) != 1:
        raise RuntimeError('Exactly one matching LSL source required')
    ring = (RustRing(args.rust_library,1024,args.channels) if args.rust_library
            else SampleRing(1024,args.channels))
    ingestion = LSLIngestion(streams[0],ring)
    count, start = 0, time.monotonic()
    try:
        while time.monotonic()-start < args.seconds:
            ingestion.poll()
            samples,_ = ring.pop(128)
            count += len(samples)
            if not len(samples):
                time.sleep(.0005)
        print(json.dumps({'received_samples':count,'dropped_samples':ring.dropped,
                          'elapsed_seconds':time.monotonic()-start}))
    finally:
        ingestion.close()
        if isinstance(ring,RustRing):
            ring.close()


if __name__ == '__main__':
    main()
