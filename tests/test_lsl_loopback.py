# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations
from pathlib import Path
import sys
import os
import threading
import time
import uuid
import numpy as np
import pytest
pylsl = pytest.importorskip('pylsl')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bin'))
from neural_ingestion import LSLIngestion,SampleRing
from neural_rust_ring import RustRing


@pytest.mark.parametrize('backend',['python','rust'])
def test_real_lsl_float32_ingestion(backend: str) -> None:
    if backend == 'rust':
        library = Path(os.environ.get('NBFM_RUST_RING','software/neural-ring/target/release/libnbfm_neural_ring.so'))
        if not library.exists():
            pytest.skip('Native LSL backend is exercised in the dedicated native CI job')
    source = 'nbfm-test-'+uuid.uuid4().hex
    info = pylsl.StreamInfo('NBFM loopback test','EEG',2,250.,'float32',source)
    outlet = pylsl.StreamOutlet(info,chunk_size=1)
    stop = threading.Event()
    def producer() -> None:
        while not stop.is_set():
            outlet.push_sample([1.,2.],pylsl.local_clock())
            stop.wait(.004)
    thread = threading.Thread(target=producer);thread.start()
    ingestion = None
    ring = None
    try:
        streams = pylsl.resolve_byprop('source_id',source,timeout=3.)
        assert len(streams) == 1
        ring = RustRing(library,1024,2) if backend == 'rust' else SampleRing(1024,2)
        ingestion = LSLIngestion(streams[0],ring)
        deadline = time.monotonic()+3
        while time.monotonic()<deadline:
            ingestion.poll();x,t = ring.pop(128)
            if len(x):
                np.testing.assert_array_equal(x,np.tile([1.,2.],(len(x),1)))
                assert np.isfinite(t).all()
                return
            time.sleep(.01)
        pytest.fail('No local LSL data received')
    finally:
        stop.set();thread.join(timeout=2.)
        if ingestion is not None:ingestion.close()
        if isinstance(ring,RustRing):ring.close()
