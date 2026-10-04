# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

import math
from typing import Dict

import torch
from torch import Tensor, nn
import torch.nn.functional as F


class CausalConv1d(nn.Module):
    def __init__(self, in_channels: int, out_channels: int, kernel_size: int,
                 stride: int = 1, dilation: int = 1, bias: bool = True) -> None:
        super().__init__()
        self.left_padding = dilation * (kernel_size - 1)
        self.conv = nn.Conv1d(in_channels, out_channels, kernel_size=kernel_size,
                              stride=stride, dilation=dilation, padding=0, bias=bias)

    def forward(self, x: Tensor) -> Tensor:
        return self.conv(F.pad(x, (self.left_padding, 0)))


class FastPatchEncoder(nn.Module):
    def __init__(self, input_channels: int, d_model: int) -> None:
        super().__init__()
        self.net = nn.Sequential(
            CausalConv1d(input_channels, d_model, 17, stride=8, bias=False),
            nn.GroupNorm(8, d_model),
            nn.GELU(),
            CausalConv1d(d_model, d_model, 5, stride=2, bias=False),
            nn.GroupNorm(8, d_model),
            nn.GELU(),
        )

    def forward(self, x: Tensor) -> Tensor:
        return self.net(x).transpose(1, 2)


class FNIRSEncoder(nn.Module):
    def __init__(self, input_channels: int, d_model: int) -> None:
        super().__init__()
        self.conv = CausalConv1d(input_channels, d_model, 3, stride=1, bias=False)
        self.norm = nn.LayerNorm(d_model)

    def forward(self, x: Tensor) -> Tensor:
        return self.norm(self.conv(x).transpose(1, 2))


class SinusoidalEncoding(nn.Module):
    def __init__(self, d_model: int, max_length: int = 4096) -> None:
        super().__init__()
        position = torch.arange(max_length, dtype=torch.float32).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2, dtype=torch.float32)
                             * (-math.log(10000.0) / d_model))
        pe = torch.zeros(max_length, d_model, dtype=torch.float32)
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        self.register_buffer("pe", pe, persistent=False)

    def forward(self, x: Tensor) -> Tensor:
        return x + self.pe[: x.shape[1]].unsqueeze(0)


class MultiHeadAttention(nn.Module):
    """ONNX/TensorRT-friendly multi-head attention using explicit matmul."""

    def __init__(self, d_model: int, num_heads: int) -> None:
        super().__init__()
        if d_model % num_heads:
            raise ValueError("d_model must be divisible by num_heads")
        self.d_model = d_model
        self.num_heads = num_heads
        self.head_dim = d_model // num_heads
        self.scale = self.head_dim ** -0.5
        self.q = nn.Linear(d_model, d_model, bias=False)
        self.k = nn.Linear(d_model, d_model, bias=False)
        self.v = nn.Linear(d_model, d_model, bias=False)
        self.o = nn.Linear(d_model, d_model, bias=False)

    def _split(self, x: Tensor) -> Tensor:
        b, t, _ = x.shape
        return x.reshape(b, t, self.num_heads, self.head_dim).transpose(1, 2)

    def forward(self, query: Tensor, key_value: Tensor, causal: bool) -> Tensor:
        q = self._split(self.q(query))
        k = self._split(self.k(key_value))
        v = self._split(self.v(key_value))
        scores = torch.matmul(q, k.transpose(-2, -1)) * self.scale
        if causal:
            tq = query.shape[1]
            tk = key_value.shape[1]
            mask = torch.triu(torch.ones((tq, tk), device=scores.device,
                                          dtype=torch.bool), diagonal=1)
            scores = scores.masked_fill(mask.view(1, 1, tq, tk), -1.0e4)
        weights = torch.softmax(scores, dim=-1)
        out = torch.matmul(weights, v)
        out = out.transpose(1, 2).contiguous().reshape(
            query.shape[0], query.shape[1], self.d_model
        )
        return self.o(out)


class NBFMBlock(nn.Module):
    def __init__(self, d_model: int, num_heads: int, ff_multiplier: int = 4) -> None:
        super().__init__()
        self.norm_self = nn.LayerNorm(d_model)
        self.self_attn = MultiHeadAttention(d_model, num_heads)
        self.norm_cross = nn.LayerNorm(d_model)
        self.cross_attn = MultiHeadAttention(d_model, num_heads)
        self.norm_ff = nn.LayerNorm(d_model)
        hidden = d_model * ff_multiplier
        self.ff = nn.Sequential(nn.Linear(d_model, hidden), nn.GELU(),
                                nn.Linear(hidden, d_model))

    def forward(self, x: Tensor, slow_context: Tensor) -> Tensor:
        q = self.norm_self(x)
        x = x + self.self_attn(q, q, causal=True)
        q = self.norm_cross(x)
        x = x + self.cross_attn(q, slow_context, causal=False)
        return x + self.ff(self.norm_ff(x))


class NBFM1(nn.Module):
    def __init__(self, eeg_channels: int = 128, meg_channels: int = 128,
                 fnirs_channels: int = 320, phoneme_vocab_size: int = 64,
                 d_model: int = 384, num_heads: int = 6, num_layers: int = 6) -> None:
        super().__init__()
        self.eeg_encoder = FastPatchEncoder(eeg_channels, d_model)
        self.meg_encoder = FastPatchEncoder(meg_channels, d_model)
        self.meg_geometry_affine = nn.Sequential(
            nn.Linear(6, 32), nn.GELU(), nn.Linear(32, 2)
        )
        self.meg_geometry_embedding = nn.Sequential(
            nn.Linear(6, 64), nn.GELU(), nn.Linear(64, d_model)
        )
        self.fast_fusion = nn.Sequential(
            nn.Linear(d_model * 2, d_model), nn.LayerNorm(d_model), nn.GELU()
        )
        self.fnirs_encoder = FNIRSEncoder(fnirs_channels, d_model)
        self.fast_position = SinusoidalEncoding(d_model)
        self.slow_position = SinusoidalEncoding(d_model)
        self.blocks = nn.ModuleList([NBFMBlock(d_model, num_heads) for _ in range(num_layers)])
        self.final_norm = nn.LayerNorm(d_model)
        self.motor_head = nn.Linear(d_model, 8)
        self.intent_head = nn.Linear(d_model, 1)
        self.speech_head = nn.Linear(d_model, phoneme_vocab_size)

    def _condition_meg(self, meg: Tensor, geometry: Tensor) -> tuple[Tensor, Tensor]:
        affine = self.meg_geometry_affine(geometry)
        scale = torch.tanh(affine[..., 0])
        bias = affine[..., 1]
        meg = meg * (1.0 + 0.10 * scale.unsqueeze(-1)) + 0.01 * bias.unsqueeze(-1)
        geom = self.meg_geometry_embedding(geometry).mean(dim=1).unsqueeze(1)
        return meg, geom

    def forward(self, eeg: Tensor, meg: Tensor, meg_geometry: Tensor,
                fnirs: Tensor) -> Dict[str, Tensor]:
        meg, geom = self._condition_meg(meg, meg_geometry)
        eeg_tokens = self.eeg_encoder(eeg)
        meg_tokens = self.meg_encoder(meg) + geom
        fast = self.fast_fusion(torch.cat((eeg_tokens, meg_tokens), dim=-1))
        fast = self.fast_position(fast)
        slow = self.slow_position(self.fnirs_encoder(fnirs))
        x = fast
        for block in self.blocks:
            x = block(x, slow)
        x = self.final_norm(x)
        state = x[:, -1]
        motor = self.motor_head(state)
        motor_mean = torch.tanh(motor[:, :4])
        motor_log_std = torch.clamp(motor[:, 4:], -6.0, 2.0)
        intent_logit = self.intent_head(state).squeeze(-1)
        speech_logits = self.speech_head(x)
        return {
            "motor_mean": motor_mean,
            "motor_log_std": motor_log_std,
            "intent_logit": intent_logit,
            "intent_probability": torch.sigmoid(intent_logit),
            "speech_ctc_logits": speech_logits,
            "speech_ctc_log_probs": F.log_softmax(speech_logits, dim=-1),
            "latent": x,
        }


def gaussian_motor_nll(target: Tensor, mean: Tensor, log_std: Tensor) -> Tensor:
    variance = torch.exp(2.0 * log_std)
    return (0.5 * (((target - mean) ** 2) / variance + 2.0 * log_std
                   + math.log(2.0 * math.pi))).mean()
