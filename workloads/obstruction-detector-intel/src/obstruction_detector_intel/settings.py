# This project was developed with assistance from AI tools.
"""obstruction-detector-intel settings."""

from common_lib.config import ServiceSettings
from pydantic import Field


class ObstructionDetectorSettings(ServiceSettings):
    service_name: str = "obstruction-detector-intel"

    # Kafka topics
    frames_topic: str = Field(default="warehouse.cameras.aisle3")
    alerts_topic: str = Field(default="fleet.safety.alerts")
    consumer_group: str = Field(default="obstruction-detector-intel")

    # YOLOv8 KServe endpoint
    yolo_endpoint_url: str = Field(
        default="http://yolov8-detector-predictor.intel-vla-training.svc.cluster.local:8081",
    )
    yolo_model: str = Field(default="yolov8m-openvino")
    yolo_request_timeout_s: float = Field(default=10.0)

    # Debounce: fire an alert only after this many consecutive same-verdict
    # frames (avoids single-frame flicker). `1` = emit on every transition.
    dwell_frames: int = Field(default=2, ge=1)

    # Aisle this detector instance covers. Phase-1 ships one detector per
    # (camera, aisle) pair; Phase-2 may consolidate if traffic volume warrants.
    aisle_id: str = Field(default="aisle-3")