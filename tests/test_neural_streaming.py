# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations
import os
from pathlib import Path
import sys
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bin'))
from neural_ingestion import SampleRing, CausalContext
from neural_preprocessing import StreamingPreprocessor, RidgeAlignment
from neural_rust_ring import RustRing
from verify_latency_evidence import verify_evidence


@pytest.mark.parametrize('backend',['python','rust'])
def test_ring_overflow_and_atomic_rejection(backend: str) -> None:
    if backend == 'rust':
        path = Path(os.environ.get('NBFM_RUST_RING','software/neural-ring/target/release/libnbfm_neural_ring.so'))
        if not path.exists():
            pytest.skip('Rust ring is exercised in the dedicated native CI job')
        ring = RustRing(path,3,2)
    else:
        ring = SampleRing(3,2)
    try:
        ring.push(np.arange(10).reshape(5,2),np.arange(5,dtype=float))
        assert ring.dropped == 2
        with pytest.raises(ValueError):
            ring.push(np.ones((1,2)),np.array([3.]))
        x,t = ring.pop(5)
        np.testing.assert_array_equal(x,np.arange(4,10).reshape(3,2))
        np.testing.assert_array_equal(t,[2,3,4])
    finally:
        if backend == 'rust':
            ring.close()
            ring.close()
            with pytest.raises(RuntimeError):
                ring.pop(1)


def test_filter_is_chunk_invariant_and_causal() -> None:
    x = np.random.default_rng(1).normal(size=(100,4))
    whole = StreamingPreprocessor(4,250.).process(x)
    split = StreamingPreprocessor(4,250.)
    blocks = np.concatenate([split.process(x[:13]),split.process(x[13:60]),split.process(x[60:])])
    np.testing.assert_allclose(whole,blocks,atol=1e-6)
    future = x.copy();future[60:] *= 1000
    np.testing.assert_array_equal(whole[:60],StreamingPreprocessor(4,250.).process(future)[:60])


def test_context_rejects_missing_stale_and_future_samples() -> None:
    context = CausalContext(2)
    context.update(1.,np.array([1,2]))
    context.update(3.,np.array([9,9]))
    np.testing.assert_array_equal(context.at(2.,1,2.),np.array([[1],[2]]))
    with pytest.raises(RuntimeError):context.at(2.,2,2.)
    with pytest.raises(RuntimeError):context.at(4.,1,.1)
    with pytest.raises(ValueError):context.update(2.,np.ones(2))


def test_ridge_alignment_needs_calibration_and_fits_known_map() -> None:
    rng = np.random.default_rng(6);x = rng.normal(size=(100,3));w = rng.normal(size=(3,2));y = x@w+2
    align = RidgeAlignment(.0001)
    with pytest.raises(RuntimeError):align.transform(x)
    align.fit(x,y)
    np.testing.assert_allclose(align.transform(x),y,atol=1e-4)


def test_latency_evidence_rejects_clock_artifacts() -> None:
    r = {'measurement_scope':'synthetic test only','clock_domain':'monotonic shared clock',
         'start_event':'sample ready','end_event':'encrypted packet received',
         'hardware':'unit test','modalities':['EEG','OPM-MEG','fNIRS'],'samples_ms':[4.]*100}
    assert verify_evidence(r)['passes_p99_budget']
    r['samples_ms'] = [-1.]*100
    with pytest.raises(ValueError):verify_evidence(r)
    r['samples_ms'] = [5.]*100
    assert not verify_evidence(r)['passes_p99_budget']
