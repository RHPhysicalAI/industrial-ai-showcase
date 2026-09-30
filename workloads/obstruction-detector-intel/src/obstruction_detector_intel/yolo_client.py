# This project was developed with assistance from AI tools.
"""YOLOv8 OpenVINO client — image → obstruction verdict via KServe."""

from __future__ import annotations

import base64
from typing import Any

import cv2
import httpx
import numpy as np
from pydantic import BaseModel, Field
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)


class ObstructionVerdict(BaseModel):
    """Match existing obstruction-detector interface."""

    obstruction: bool
    label: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    detail: str = ""


# COCO class names (YOLOv8 uses COCO dataset - 80 classes)
COCO_CLASSES = [
    'person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train', 'truck',
    'boat', 'traffic light', 'fire hydrant', 'stop sign', 'parking meter', 'bench',
    'bird', 'cat', 'dog', 'horse', 'sheep', 'cow', 'elephant', 'bear', 'zebra',
    'giraffe', 'backpack', 'umbrella', 'handbag', 'tie', 'suitcase', 'frisbee',
    'skis', 'snowboard', 'sports ball', 'kite', 'baseball bat', 'baseball glove',
    'skateboard', 'surfboard', 'tennis racket', 'bottle', 'wine glass', 'cup',
    'fork', 'knife', 'spoon', 'bowl', 'banana', 'apple', 'sandwich', 'orange',
    'broccoli', 'carrot', 'hot dog', 'pizza', 'donut', 'cake', 'chair', 'couch',
    'potted plant', 'bed', 'dining table', 'toilet', 'tv', 'laptop', 'mouse',
    'remote', 'keyboard', 'cell phone', 'microwave', 'oven', 'toaster', 'sink',
    'refrigerator', 'book', 'clock', 'vase', 'scissors', 'teddy bear', 'hair drier',
    'toothbrush'
]

# Warehouse-relevant classes for obstruction detection
OBSTRUCTION_CLASSES = {
    'person', 'bicycle', 'car', 'motorcycle', 'truck', 'chair',
    'couch', 'potted plant', 'backpack', 'suitcase', 'handbag'
}


class YoloClient:
    """YOLOv8 inference client for KServe endpoint."""

    def __init__(self, endpoint_url: str, timeout_s: float = 10.0) -> None:
        self._endpoint_url = endpoint_url
        self._client = httpx.AsyncClient(timeout=timeout_s)

    async def aclose(self) -> None:
        await self._client.aclose()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, max=3.0),
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
        reraise=True,
    )
    async def reason(self, image_b64: str, _prompt: str = "") -> ObstructionVerdict:
        """
        Detect obstructions in image using YOLOv8.

        Args:
            image_b64: Base64-encoded JPEG image
            _prompt: Unused (for API compatibility with CosmosClient)

        Returns:
            ObstructionVerdict with detection results
        """
        # Decode image
        img_bytes = base64.b64decode(image_b64)
        img_array = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

        if img is None:
            return ObstructionVerdict(
                obstruction=False,
                confidence=0.0,
                detail="Failed to decode image"
            )

        # Preprocess for YOLOv8 (640x640, RGB, normalized, NCHW)
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img_resized = cv2.resize(img_rgb, (640, 640))
        img_normalized = img_resized.astype(np.float32) / 255.0
        img_transposed = np.transpose(img_normalized, (2, 0, 1))
        img_batch = np.expand_dims(img_transposed, axis=0)

        # Build KServe v2 request
        request_body = {
            "inputs": [{
                "name": "x.1",  # Input name from model metadata
                "shape": list(img_batch.shape),
                "datatype": "FP32",
                "data": img_batch.flatten().tolist()
            }]
        }

        # Call KServe
        resp = await self._client.post(
            f"{self._endpoint_url}/v2/models/yolov8-detector/infer",
            json=request_body
        )
        resp.raise_for_status()

        result = resp.json()

        # Parse detections
        return self._parse_detections(result)

    def _parse_detections(self, kserve_response: dict[str, Any]) -> ObstructionVerdict:
        """Parse KServe response into ObstructionVerdict."""
        outputs = kserve_response.get("outputs", [])

        if not outputs:
            return ObstructionVerdict(
                obstruction=False,
                confidence=0.0,
                detail="No detections in response"
            )

        # Extract detection data - YOLOv8 output: [1, 84, 8400]
        # 84 = 4 bbox coords (x, y, w, h) + 80 class scores
        output_data = np.array(outputs[0]["data"], dtype=np.float32)
        output_shape = outputs[0]["shape"]

        detections_raw = output_data.reshape(output_shape)

        # Squeeze batch dimension and transpose to [8400, 84]
        detections_raw = detections_raw.squeeze(0).T  # [84, 8400] -> [8400, 84]

        # Find highest-confidence obstruction
        best_detection = None
        max_conf = 0.0

        for pred in detections_raw:
            # pred: [x, y, w, h, conf_class0, conf_class1, ..., conf_class79]
            bbox = pred[:4]
            class_scores = pred[4:]

            class_id = int(np.argmax(class_scores))
            confidence = float(class_scores[class_id])

            if confidence < 0.5:
                continue

            class_name = COCO_CLASSES[class_id] if class_id < len(COCO_CLASSES) else 'unknown'

            if class_name in OBSTRUCTION_CLASSES and confidence > max_conf:
                max_conf = confidence
                best_detection = {
                    'class_name': class_name,
                    'confidence': confidence,
                    'bbox': bbox.tolist()
                }

        if best_detection:
            return ObstructionVerdict(
                obstruction=True,
                label=best_detection['class_name'],
                confidence=max_conf,
                detail=f"Detected {best_detection['class_name']} at bbox {best_detection['bbox']}"
            )
        else:
            return ObstructionVerdict(
                obstruction=False,
                label="clear",
                confidence=1.0,
                detail="No obstructions detected"
            )