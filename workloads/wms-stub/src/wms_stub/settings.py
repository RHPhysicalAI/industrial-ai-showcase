# This project was developed with assistance from AI tools.
"""WMS-Stub settings — extends common_lib.ServiceSettings."""

from pydantic import Field

from common_lib.config import ServiceSettings


class WmsStubSettings(ServiceSettings):
    service_name: str = "wms-stub"

    missions_topic: str = "fleet.missions"
    telemetry_topic: str = "fleet.telemetry"

    camera_commands_topic: str = Field(
        default="warehouse.cameras.commands",
        description="Kafka topic for camera state-change commands consumed by fake-camera.",
    )
    alerts_topic: str = Field(
        default="fleet.safety.alerts",
        description="Safety-alert topic consumed by Fleet Manager and the digital twin.",
    )
    camera_id: str = Field(default="cam-aisle-3")
    camera_aisle_id: str = Field(default="aisle-3")

    default_robot_id: str = "fl-07"
    default_route_aisle: str = "aisle-3"
    default_destination: str = "dock-b"
    policy_version: str = "vla-warehouse-v1.3"
