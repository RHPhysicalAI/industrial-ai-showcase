# This project was developed with assistance from AI tools.
"""VLA model adapters — each returns a 7-DOF action vector for a given (image, instruction)."""

from __future__ import annotations

import base64
import io
import random
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import numpy as np

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


_IMAGE_PATTERNS = {"image", "pixel", "vision", "img"}
_TEXT_PATTERNS = {"token", "input_ids"}
_MASK_PATTERNS = {"attention", "mask"}


class OnnxAdapter:
    """ONNX Runtime adapter for VLA models exported by NVIDIA's build_trt_pipeline."""

    def __init__(self, model_dir: str, device: str = "cuda") -> None:
        self._model_dir = model_dir
        self._device = device
        self._session = None
        self.model_version = f"onnx-{Path(model_dir).name}"

    def _ensure_loaded(self) -> None:
        if self._session is not None:
            return
        import onnxruntime as ort  # type: ignore[import-not-found]

        providers = (
            ["CUDAExecutionProvider", "CPUExecutionProvider"]
            if self._device == "cuda"
            else ["CPUExecutionProvider"]
        )

        onnx_files = sorted(Path(self._model_dir).glob("**/*.onnx"))
        if not onnx_files:
            raise FileNotFoundError(f"No .onnx files found in {self._model_dir}")

        main_model = max(onnx_files, key=lambda p: p.stat().st_size)
        self._session = ort.InferenceSession(str(main_model), providers=providers)

    def _preprocess_image(self, image: Image, shape: list) -> np.ndarray:
        h, w, layout = 224, 224, "nchw"
        if len(shape) == 4:
            if isinstance(shape[1], int) and shape[1] in (1, 3):
                h = shape[2] if isinstance(shape[2], int) and shape[2] > 0 else 224
                w = shape[3] if isinstance(shape[3], int) and shape[3] > 0 else 224
                layout = "nchw"
            else:
                h = shape[1] if isinstance(shape[1], int) and shape[1] > 0 else 224
                w = shape[2] if isinstance(shape[2], int) and shape[2] > 0 else 224
                layout = "nhwc"

        img = image.resize((w, h))
        arr = np.array(img, dtype=np.float32) / 255.0
        if layout == "nchw":
            arr = arr.transpose(2, 0, 1)
        return np.expand_dims(arr, axis=0)

    def _prepare_feed(self, image: Image, instruction: str) -> dict:
        feed: dict[str, np.ndarray] = {}
        for inp in self._session.get_inputs():  # type: ignore[union-attr]
            name_lower = inp.name.lower()
            shape = [d if isinstance(d, int) and d > 0 else 1 for d in inp.shape]

            if any(p in name_lower for p in _IMAGE_PATTERNS):
                feed[inp.name] = self._preprocess_image(image, inp.shape)
            elif any(p in name_lower for p in _TEXT_PATTERNS):
                seq_len = shape[-1] if shape else 64
                tokens = [ord(c) % 32000 for c in instruction[:seq_len]]
                arr = np.zeros(shape, dtype=np.int64)
                arr.flat[: len(tokens)] = tokens
                feed[inp.name] = arr
            elif any(p in name_lower for p in _MASK_PATTERNS):
                feed[inp.name] = np.ones(shape, dtype=np.int64)
            else:
                dtype_str = (inp.type or "").lower()
                if "float" in dtype_str:
                    feed[inp.name] = np.zeros(shape, dtype=np.float32)
                else:
                    feed[inp.name] = np.zeros(shape, dtype=np.int64)
        return feed

    def infer(self, image: Image, instruction: str) -> list[float]:
        self._ensure_loaded()
        feed = self._prepare_feed(image, instruction)
        outputs = self._session.run(None, feed)  # type: ignore[union-attr]
        action = outputs[0].flatten().tolist()
        return action[:7] if len(action) >= 7 else action


_G1_STATE_DIMS = {
    "left_leg": 6, "right_leg": 6, "waist": 3,
    "left_arm": 7, "left_hand": 7, "right_arm": 7, "right_hand": 7,
}
_G1_ACTION_KEYS = list(_G1_STATE_DIMS.keys())


class GR00TAdapter:
    """GR00T N1.7 adapter using Gr00tPolicy for real VLA inference."""

    _BUILTIN_TAGS = {"REAL_G1", "XDOF", "XDOF_SUBTASK", "OXE_DROID_RELATIVE_EEF_RELATIVE_JOINT"}

    def __init__(self, model_path: str, embodiment_tag: str = "REAL_G1", device: str = "cuda") -> None:
        self._model_path = model_path
        self._embodiment_tag = embodiment_tag
        self._device = device
        self._policy = None
        self._video_key = "ego_view"
        self.model_version = f"groot-{Path(model_path).name}"

    def _register_custom_embodiment(self) -> None:
        from gr00t.configs.data.embodiment_configs import register_modality_config  # type: ignore[import-not-found]
        from gr00t.data.embodiment_tags import EmbodimentTag  # type: ignore[import-not-found]
        from gr00t.data.types import (  # type: ignore[import-not-found]
            ActionConfig, ActionFormat, ActionRepresentation, ActionType, ModalityConfig,
        )

        config = {
            "video": ModalityConfig(delta_indices=[0], modality_keys=[self._video_key]),
            "state": ModalityConfig(delta_indices=[0], modality_keys=_G1_ACTION_KEYS),
            "action": ModalityConfig(
                delta_indices=list(range(16)),
                modality_keys=_G1_ACTION_KEYS,
                action_configs=[
                    ActionConfig(
                        rep=ActionRepresentation.RELATIVE if k in ("left_arm", "right_arm")
                        else ActionRepresentation.ABSOLUTE,
                        type=ActionType.NON_EEF, format=ActionFormat.DEFAULT,
                    )
                    for k in _G1_ACTION_KEYS
                ],
            ),
            "language": ModalityConfig(delta_indices=[0], modality_keys=["task_description"]),
        }
        register_modality_config(config, embodiment_tag=EmbodimentTag[self._embodiment_tag])

    def _ensure_loaded(self) -> None:
        if self._policy is not None:
            return
        from gr00t.policy.gr00t_policy import Gr00tPolicy  # type: ignore[import-not-found]

        if self._embodiment_tag not in self._BUILTIN_TAGS:
            self._register_custom_embodiment()
        self._policy = Gr00tPolicy(
            embodiment_tag=self._embodiment_tag,
            model_path=self._model_path,
            device=self._device,
        )

    def infer(self, image: Image, instruction: str) -> list[float]:
        self._ensure_loaded()
        assert self._policy is not None

        img_arr = np.array(image, dtype=np.uint8)
        if img_arr.ndim == 2:
            img_arr = np.stack([img_arr] * 3, axis=-1)
        # Gr00tPolicy expects: video -> {key: (B, T, H, W, C)}, state -> {key: (B, T, D)},
        # language -> {key: [[str]]}
        obs: dict = {
            "video": {self._video_key: img_arr[np.newaxis, np.newaxis, ...]},
            "state": {part: np.zeros((1, 1, dim), dtype=np.float32) for part, dim in _G1_STATE_DIMS.items()},
            "language": {"task_description": [[instruction]]},
        }

        action_chunk, _ = self._policy.get_action(obs)
        action: list[float] = []
        for key in action_chunk:
            vals = action_chunk[key]
            if hasattr(vals, "tolist"):
                action.extend(vals.flatten().tolist())
            elif isinstance(vals, list):
                action.extend(vals)
        return action[:7] if len(action) >= 7 else action


def _is_onnx_dir(path: str) -> bool:
    p = Path(path)
    if not p.is_dir():
        return False
    has_onnx = any(p.glob("**/*.onnx"))
    has_hf_config = (p / "config.json").exists()
    return has_onnx and not has_hf_config


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
    groot_model_path: str = "",
    groot_embodiment_tag: str = "NEW_EMBODIMENT",
) -> VlaAdapter:
    mode = mode.lower()
    if mode == "mock":
        return MockAdapter()
    if mode == "groot":
        model_path = groot_model_path or weights
        resolved = _resolve_weights(model_path, s3_endpoint=s3_endpoint, model_cache_dir=model_cache_dir)
        return GR00TAdapter(model_path=resolved, embodiment_tag=groot_embodiment_tag, device=device)
    if mode in ("openvla", "onnx"):
        resolved = _resolve_weights(weights, s3_endpoint=s3_endpoint, model_cache_dir=model_cache_dir)
        if _is_onnx_dir(resolved) or mode == "onnx":
            return OnnxAdapter(model_dir=resolved, device=device)
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
