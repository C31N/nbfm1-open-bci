# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations
from pathlib import Path
import sys
import numpy as np
import pytest
torch = pytest.importorskip('torch')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bin'))
from nbfm1 import FastPatchEncoder, NBFM1
from neural_decoder import MaskedAutoencoder, ReferenceDecoder, MultimodalPipeline


def test_fast_encoder_has_no_future_normalization_leakage() -> None:
    torch.set_num_threads(1);torch.manual_seed(1)
    encoder = FastPatchEncoder(4,16).eval();x = torch.randn(1,4,64)
    changed = x.clone();changed[:,:,32:] += 100
    torch.testing.assert_close(encoder(x)[:,:2],encoder(changed)[:,:2])


def test_mae_has_finite_trainable_masked_loss() -> None:
    torch.manual_seed(2)
    model = NBFM1(eeg_channels=4,meg_channels=4,fnirs_channels=6,
                   d_model=16,num_heads=4,num_layers=1)
    mae = MaskedAutoencoder(model,4,16)
    eeg,meg = torch.randn(2,4,32),torch.randn(2,4,32)
    geometry,slow = torch.randn(2,4,6),torch.randn(2,6,2)
    loss = mae(eeg,meg,geometry,slow,torch.tensor([[True,False],[False,True]]))
    loss.backward()
    assert torch.isfinite(loss)
    assert mae.reconstruct.weight.grad is not None


def test_multimodal_pipeline_requires_real_slow_context() -> None:
    torch.manual_seed(3)
    decoder = ReferenceDecoder(NBFM1(d_model=16,num_heads=4,num_layers=1))
    pipeline = MultimodalPipeline(decoder,np.zeros((1,128,6),np.float32),window=16,slow_samples=1)
    x = np.random.default_rng(4).normal(size=(16,128));t = 1.+np.arange(16)/250
    with pytest.raises(RuntimeError):pipeline.process(x,x,t)
    pipeline.context.update(1.,np.ones(320))
    result = pipeline.process(x[:1],x[:1],np.array([1.1]))
    assert result['motor_mean'].shape == (1,4)
    assert np.isfinite(result['speech_ctc_logits']).all()
