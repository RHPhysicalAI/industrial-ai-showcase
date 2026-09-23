# This project was developed with assistance from AI tools.
"""VLA model adapters — each preserves the public 7-value action API."""

from __future__ import annotations

import base64
import io
import random
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Protocol

import numpy as np

from openvla_server.action_contract import (
    TELEOP_G1_ACTION_DIMS,
    TELEOP_G1_ACTION_KEYS,
    legacy_7_value_compatibility_projection,
    validate_teleop_g1_action_chunk,
)

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
        from transformers import (  # type: ignore[import-not-found]
            AutoModelForVision2Seq,
            AutoProcessor,
        )

        dtype = {"fp16": torch.float16, "bf16": torch.bfloat16, "fp32": torch.float32}[self._torch_dtype]
        self._processor = AutoProcessor.from_pretrained(self._weights, trust_remote_code=True)
        self._model = AutoModelForVision2Seq.from_pretrained(
            self._weights,
            # OpenVLA's custom model class does not implement Transformers' SDPA capability hook.
            # Keep the legacy-compatible eager attention path explicit.
            attn_implementation="eager",
            torch_dtype=dtype,
            # The CUDA image uses low_cpu_mem_usage, which initializes parameters on
            # the meta device. Let Transformers place the loaded model instead of
            # calling .to(cuda) on meta-backed parameters afterward.
            device_map="auto",
            low_cpu_mem_usage=True,
            trust_remote_code=True,
        )
        self._model.eval()

    def infer(self, image: Image, instruction: str) -> list[float]:
        self._ensure_loaded()
        assert self._processor is not None and self._model is not None
        import torch  # type: ignore[import-not-found]

        prompt = f"In: What action should the robot take to {instruction}?\nOut:"
        inputs = self._processor(prompt, image).to(self._device, dtype=self._model.dtype)

        # The legacy OpenVLA remote wrapper appends the special empty output token
        # (29871) to input_ids inside predict_action(), but leaves attention_mask
        # unchanged.  Transformers then builds a multimodal mask that is one token
        # shorter than the generated input. Keep the original wrapper contract and
        # extend only the matching mask before handing inputs to predict_action().
        input_ids = inputs.get("input_ids")
        attention_mask = inputs.get("attention_mask")
        if input_ids is not None and attention_mask is not None:
            needs_output_token = any(int(token) != 29871 for token in input_ids[:, -1].tolist())
            if needs_output_token and attention_mask.shape[-1] == input_ids.shape[-1]:
                inputs["attention_mask"] = torch.cat(
                    [attention_mask, attention_mask.new_ones((attention_mask.shape[0], 1))], dim=-1
                )

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
    "left_wrist_eef_9d": 9, "right_wrist_eef_9d": 9,
    "left_hand": 7, "right_hand": 7,
    "left_arm": 7, "right_arm": 7, "waist": 3,
}
_G1_ACTION_KEYS = list(_G1_STATE_DIMS.keys())

_TELEOP_G1_STATE_DIMS = TELEOP_G1_ACTION_DIMS


def _build_g1_state_placeholder() -> dict[str, np.ndarray]:
    """Build a numerically safe placeholder state for REAL_G1.

    EEF 9D keys use XYZ_ROT6D format: [x,y,z, col0(3), col1(3)] where col0/col1
    are the first two columns of a rotation matrix. Identity rotation avoids SVD
    divergence on all-zeros input.
    """
    identity_rot6d = np.array([1, 0, 0, 0, 1, 0], dtype=np.float32)
    state: dict[str, np.ndarray] = {}
    for part, dim in _G1_STATE_DIMS.items():
        if part.endswith("_eef_9d"):
            val = np.concatenate([np.zeros(3, dtype=np.float32), identity_rot6d])
            state[part] = val.reshape(1, 1, dim)
        else:
            state[part] = np.zeros((1, 1, dim), dtype=np.float32)
    return state


def _build_teleop_g1_state_placeholder() -> dict[str, np.ndarray]:
    """Build a zero state matching the Teleop-G1 43-DOF joint schema."""
    return {
        part: np.zeros((1, 1, dim), dtype=np.float32)
        for part, dim in _TELEOP_G1_STATE_DIMS.items()
    }


class GR00TAdapter:
    """GR00T N1.7 adapter using Gr00tPolicy for real VLA inference.

    The Teleop-G1 training contract is wider than the existing robot-edge
    HTTP contract: its state/action modality has 43 joint values, while the
    deployed Mission Dispatcher integration consumes the established 7-value
    response. Keep that boundary explicit until downstream action mapping is
    validated; this adapter must not silently change the live demo contract.
    """

    _BUILTIN_TAGS: ClassVar[set[str]] = {
        "REAL_G1", "XDOF", "XDOF_SUBTASK", "OXE_DROID_RELATIVE_EEF_RELATIVE_JOINT"
    }

    def __init__(
        self,
        model_path: str,
        embodiment_tag: str = "REAL_G1",
        device: str = "cuda",
        video_key: str = "ego_view",
    ) -> None:
        self._model_path = model_path
        self._embodiment_tag = embodiment_tag
        self._device = device
        self._policy = None
        self._video_key = video_key
        self._video_horizon = 2
        self.model_version = f"groot-{Path(model_path).name}"

    def _register_custom_embodiment(self) -> None:
        from gr00t.configs.data.embodiment_configs import (  # type: ignore[import-not-found]
            register_modality_config,
        )
        from gr00t.data.embodiment_tags import EmbodimentTag  # type: ignore[import-not-found]
        from gr00t.data.types import (  # type: ignore[import-not-found]
            ActionConfig,
            ActionFormat,
            ActionRepresentation,
            ActionType,
            ModalityConfig,
        )

        config = {
            "video": ModalityConfig(delta_indices=[0], modality_keys=[self._video_key]),
            "state": ModalityConfig(delta_indices=[0], modality_keys=list(TELEOP_G1_ACTION_KEYS)),
            "action": ModalityConfig(
                delta_indices=list(range(16)),
                modality_keys=list(TELEOP_G1_ACTION_KEYS),
                action_configs=[
                    ActionConfig(
                        rep=ActionRepresentation.RELATIVE if k in ("left_arm", "right_arm")
                        else ActionRepresentation.ABSOLUTE,
                        type=ActionType.NON_EEF, format=ActionFormat.DEFAULT,
                    )
                    for k in TELEOP_G1_ACTION_KEYS
                ],
            ),
            "language": ModalityConfig(delta_indices=[0], modality_keys=["annotation.human.task_description"]),
        }
        register_modality_config(config, embodiment_tag=EmbodimentTag[self._embodiment_tag])

    def _ensure_loaded(self) -> None:
        if self._policy is not None:
            return
        from gr00t.policy.gr00t_policy import Gr00tPolicy  # type: ignore[import-not-found]

        if self._embodiment_tag not in self._BUILTIN_TAGS:
            self._video_horizon = 1
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
        # REAL_G1 uses delta_indices=[0,1]; the custom Teleop-G1 modality uses
        # delta_indices=[0]. Duplicate only when the selected modality requires it.
        video_frames = np.stack([img_arr] * self._video_horizon, axis=0)
        obs: dict = {
            "video": {self._video_key: video_frames[np.newaxis, ...]},
            "state": (
                _build_teleop_g1_state_placeholder()
                if self._embodiment_tag == "NEW_EMBODIMENT"
                else _build_g1_state_placeholder()
            ),
            "language": {"annotation.human.task_description": [[instruction]]},
        }

        action_chunk, _ = self._policy.get_action(obs)
        if self._embodiment_tag == "NEW_EMBODIMENT":
            validate_teleop_g1_action_chunk(action_chunk)
        action: list[float] = []
        for key in action_chunk:
            vals = action_chunk[key]
            if hasattr(vals, "tolist"):
                action.extend(vals.flatten().tolist())
            elif isinstance(vals, list):
                action.extend(vals)
        return legacy_7_value_compatibility_projection(action)


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
    groot_video_key: str = "ego_view",
) -> VlaAdapter:
    mode = mode.lower()
    if mode == "mock":
        return MockAdapter()
    if mode == "groot":
        model_path = groot_model_path or weights
        resolved = _resolve_weights(model_path, s3_endpoint=s3_endpoint, model_cache_dir=model_cache_dir)
        return GR00TAdapter(
            model_path=resolved,
            embodiment_tag=groot_embodiment_tag,
            device=device,
            video_key=groot_video_key,
        )
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
