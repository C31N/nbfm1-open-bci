# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np


class TensorRTRunner:
    """Static-shape TensorRT 10.x runner with persistent pinned/device buffers."""

    def __init__(self, engine_path: str) -> None:
        import tensorrt as trt

        try:
            from cuda.bindings import runtime as cudart
        except ImportError:
            from cuda import cudart

        self.trt = trt
        self.cudart = cudart
        self.logger = trt.Logger(trt.Logger.ERROR)
        self.runtime = trt.Runtime(self.logger)
        self.engine = self.runtime.deserialize_cuda_engine(
            Path(engine_path).read_bytes()
        )
        if self.engine is None:
            raise RuntimeError("failed to deserialize TensorRT engine")

        self.context = self.engine.create_execution_context()
        err, self.stream = self.cudart.cudaStreamCreate()
        self._check(err)

        self.host: dict[str, np.ndarray] = {}
        self.device: dict[str, int] = {}
        self.is_input: dict[str, bool] = {}

        for index in range(self.engine.num_io_tensors):
            name = self.engine.get_tensor_name(index)
            shape = tuple(int(value) for value in self.engine.get_tensor_shape(name))
            if any(value <= 0 for value in shape):
                raise RuntimeError(f"dynamic TensorRT shape {name}: {shape}")

            dtype = np.dtype(trt.nptype(self.engine.get_tensor_dtype(name)))
            array = np.empty(shape, dtype=dtype, order="C")

            self._check(
                self.cudart.cudaHostRegister(
                    array.ctypes.data,
                    array.nbytes,
                    0,
                )[0]
            )
            err, pointer = self.cudart.cudaMalloc(array.nbytes)
            self._check(err)

            self.host[name] = array
            self.device[name] = int(pointer)
            self.is_input[name] = (
                self.engine.get_tensor_mode(name) == trt.TensorIOMode.INPUT
            )

            if not self.context.set_tensor_address(name, int(pointer)):
                raise RuntimeError(f"failed to bind TensorRT tensor {name}")

    @staticmethod
    def _check(err: Any) -> None:
        if int(err) != 0:
            raise RuntimeError(f"CUDA runtime error {err}")

    def infer(self, inputs: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        kind = self.cudart.cudaMemcpyKind

        for name, source in inputs.items():
            host = self.host[name]
            np.copyto(
                host,
                np.asarray(source, dtype=host.dtype).reshape(host.shape),
                casting="unsafe",
            )
            self._check(
                self.cudart.cudaMemcpyAsync(
                    self.device[name],
                    host.ctypes.data,
                    host.nbytes,
                    kind.cudaMemcpyHostToDevice,
                    self.stream,
                )[0]
            )

        if not self.context.execute_async_v3(stream_handle=self.stream):
            raise RuntimeError("TensorRT execute_async_v3 failed")

        for name, host in self.host.items():
            if self.is_input[name]:
                continue
            self._check(
                self.cudart.cudaMemcpyAsync(
                    host.ctypes.data,
                    self.device[name],
                    host.nbytes,
                    kind.cudaMemcpyDeviceToHost,
                    self.stream,
                )[0]
            )

        self._check(self.cudart.cudaStreamSynchronize(self.stream)[0])
        return {
            name: array.copy()
            for name, array in self.host.items()
            if not self.is_input[name]
        }

    def close(self) -> None:
        for name, array in self.host.items():
            try:
                self.cudart.cudaHostUnregister(array.ctypes.data)
            except Exception:
                print(f"warning: failed to unregister pinned buffer {name}")

            try:
                self.cudart.cudaFree(self.device[name])
            except Exception:
                print(f"warning: failed to free CUDA buffer {name}")

        try:
            self.cudart.cudaStreamDestroy(self.stream)
        except Exception:
            print("warning: failed to destroy CUDA stream")


class ORTRunner:
    def __init__(self, model_path: str, cache_path: str) -> None:
        import onnxruntime as ort

        available = ort.get_available_providers()
        providers: list[Any] = []

        if "TensorrtExecutionProvider" in available:
            providers.append(
                (
                    "TensorrtExecutionProvider",
                    {
                        "device_id": 0,
                        "trt_engine_cache_enable": True,
                        "trt_engine_cache_path": cache_path,
                        "trt_timing_cache_enable": True,
                        "trt_timing_cache_path": cache_path,
                        "trt_fp16_enable": True,
                        "trt_cuda_graph_enable": True,
                    },
                )
            )

        if "CUDAExecutionProvider" in available:
            providers.append(("CUDAExecutionProvider", {"device_id": 0}))

        providers.append("CPUExecutionProvider")

        options = ort.SessionOptions()
        options.graph_optimization_level = (
            ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        )

        self.session = ort.InferenceSession(
            model_path,
            sess_options=options,
            providers=providers,
        )

    def infer(self, inputs: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        names = [output.name for output in self.session.get_outputs()]
        values = self.session.run(names, inputs)
        return dict(zip(names, values, strict=True))

    def close(self) -> None:
        return None
