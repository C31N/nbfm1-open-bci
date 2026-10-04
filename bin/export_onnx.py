# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations
import argparse
from pathlib import Path
import torch
from nbfm1 import NBFM1

class ExportWrapper(torch.nn.Module):
    def __init__(self, model: NBFM1) -> None:
        super().__init__(); self.model = model
    def forward(self, eeg, meg, meg_geometry, fnirs):
        result = self.model(eeg, meg, meg_geometry, fnirs)
        return result["motor_mean"], result["motor_log_std"], result["intent_logit"], result["speech_ctc_logits"]

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--output", default="/opt/bci-stack/models/nbfm1.onnx")
    p.add_argument("--checkpoint", default="")
    p.add_argument("--fast-samples", type=int, default=512)
    p.add_argument("--fnirs-samples", type=int, default=20)
    args = p.parse_args()
    torch.manual_seed(0)
    model = NBFM1()
    if args.checkpoint:
        state = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
        model.load_state_dict(state, strict=True)
    model.eval(); wrapper = ExportWrapper(model).eval()
    inputs = (
        torch.zeros(1,128,args.fast_samples),
        torch.zeros(1,128,args.fast_samples),
        torch.zeros(1,128,6),
        torch.zeros(1,320,args.fnirs_samples),
    )
    output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(wrapper, inputs, str(output),
        input_names=["eeg","meg","meg_geometry","fnirs"],
        output_names=["motor_mean","motor_log_std","intent_logit","speech_ctc_logits"],
        opset_version=18, do_constant_folding=True, dynamic_axes=None, dynamo=False)
    print(output)

if __name__ == "__main__":
    main()
