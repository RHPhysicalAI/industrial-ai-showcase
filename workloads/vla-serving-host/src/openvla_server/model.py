# This project was developed with assistance from AI tools.
"""VLA model adapters — each returns a 7-DOF action vector for a given (image, instruction)."""

from __future__ import annotations

import base64
import io
import random
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from PIL.Image import Image


class VlaAdapter(Protocol):
    """A VLA model adapter: PIL image + instruction → 7-DOF action vector."""

    model_version: str

    def infer(self, image: Image, instruction: str) -> list[float]: ...


class MockAdapter:
    """Deterministic stub — returns a pseudo-random 7-DOF vector seeded on the instruction.

    Used to prove the wiring (SNO pod → bridge → this server → back) without requiring
    the real model + ROCm bring-up. Flip `VLA_MODE=openvla` once you're ready for real inference.
    """

    model_version = "mock-v0"

    def infer(self, image: Image, instruction: str) -> list[float]:
        rng = random.Random(hash(instruction) & 0xFFFFFFFF)
        return [round(rng.uniform(-0.3, 0.3), 4) for _ in range(6)] + [float(rng.randint(0, 1))]


class OpenvlaAdapter:
    """Real OpenVLA-7B adapter. Loads HuggingFace weights on first `infer`."""

    def __init__(self, weights: str, unnorm_key: str, device: str, torch_dtype: str = "fp16") -> None:
        self._weights = weights
        self._unnorm_key = unnorm_key
        self._device = device
        self._torch_dtype = torch_dtype
        self._model = None
        self._processor = None
        self.model_version = f"openvla-{weights.split('/')[-1]}"

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        # Deferred import — PyTorch + transformers are heavy and only pulled when we need them.
        import torch  # type: ignore[import-not-found]
        from transformers import AutoModelForVision2Seq, AutoProcessor  # type: ignore[import-not-found]

        dtype = {"fp16": torch.float16, "bf16": torch.bfloat16, "fp32": torch.float32}[self._torch_dtype]
        self._processor = AutoProcessor.from_pretrained(self._weights, trust_remote_code=True)
        self._model = AutoModelForVision2Seq.from_pretrained(
            self._weights,
            torch_dtype=dtype,
            low_cpu_mem_usage=True,
            trust_remote_code=True,
        ).to(self._device)
        self._model.eval()

    def infer(self, image: Image, instruction: str) -> list[float]:
        self._ensure_loaded()
        assert self._processor is not None and self._model is not None

        prompt = f"In: What action should the robot take to {instruction}?\nOut:"
        inputs = self._processor(prompt, image).to(self._device, dtype=self._model.dtype)
        action = self._model.predict_action(**inputs, unnorm_key=self._unnorm_key, do_sample=False)
        return list(action.tolist() if hasattr(action, "tolist") else action)


def _resolve_weights(weights: str, s3_endpoint: str = "", model_cache_dir: str = "/tmp/model_cache") -> str:
    """Resolve an s3:// URI to a local path; pass through HF ids and local paths unchanged."""
    if not weights.startswith("s3://"):
        return weights
    from openvla_server.s3_loader import download_model_from_s3

    return download_model_from_s3(uri=weights, local_dir=model_cache_dir, endpoint=s3_endpoint)


def build_adapter(
    mode: str,
    weights: str,
    unnorm_key: str,
    device: str,
    torch_dtype: str = "fp16",
    s3_endpoint: str = "",
    model_cache_dir: str = "/tmp/model_cache",
) -> VlaAdapter:
    mode = mode.lower()
    if mode == "mock":
        return MockAdapter()
    if mode == "openvla":
        resolved = _resolve_weights(weights, s3_endpoint=s3_endpoint, model_cache_dir=model_cache_dir)
        return OpenvlaAdapter(
            weights=resolved, unnorm_key=unnorm_key, device=device, torch_dtype=torch_dtype
        )
    if mode in {"smolvla", "pi0"}:
        raise NotImplementedError(f"{mode} adapter lands in Phase 3 — see workloads/vla-serving-host/README.md.")
    raise ValueError(f"Unknown VLA_MODE: {mode!r}")


def decode_image_b64(image_b64: str) -> Image:
    """Decode a base64-encoded image into a PIL RGB Image, or return a black placeholder if empty."""
    from PIL import Image as PILImage

    if not image_b64:
        return PILImage.new("RGB", (224, 224), (0, 0, 0))
    raw = base64.b64decode(image_b64)
    img = PILImage.open(io.BytesIO(raw)).convert("RGB")
    return img
